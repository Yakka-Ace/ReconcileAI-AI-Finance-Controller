"""
Core agentic workflow: ReconcileAgent.

Design choice (see README "Technical Obstacles"): rather than trusting
the LLM to do arithmetic and database lookups from memory (a major
hallucination source), the agent exposes deterministic Python *tools*
for every factual lookup. The LLM's only job is to weigh the evidence
those tools return and produce a structured verdict. This keeps the
model's role to judgment, not computation.

Flow per transaction:
  1. tool: get_invoice()            -> ground truth billed amount
  2. tool: get_merchant_stats()     -> mean/std of merchant's history
  3. tool: check_duplicate()        -> flags repeat transaction_ids
  4. rule engine computes a z-score + threshold pre-flag
  5. LLM receives ALL of the above as evidence and returns a
     schema-validated AgentVerdict (LangChain structured output —
     the model literally cannot return anything that fails validation)
"""
import statistics
import uuid
from datetime import timedelta
from sqlalchemy.orm import Session

from database import Transaction, Invoice, AnalysisLog
from schemas import AgentVerdict
from llm_utils import get_chat_model, call_with_retry, build_messages
from config import settings


# ---------------------------------------------------------------------------
# Deterministic tools (plain Python — no LLM involved, fully auditable)
# ---------------------------------------------------------------------------

def tool_get_invoice(db: Session, invoice_ref: str | None) -> dict:
    if not invoice_ref:
        return {"found": False, "reason": "no invoice_ref on transaction"}
    inv = db.query(Invoice).filter(Invoice.invoice_ref == invoice_ref).first()
    if not inv:
        return {"found": False, "reason": f"invoice {invoice_ref} not found in ledger"}
    return {
        "found": True,
        "billed_amount": inv.billed_amount,
        "status": inv.status,
        "due_date": str(inv.due_date),
    }


def tool_get_merchant_stats(db: Session, merchant_id: str, exclude_txn_id: str) -> dict:
    rows = (
        db.query(Transaction.amount)
        .filter(Transaction.merchant_id == merchant_id, Transaction.transaction_id != exclude_txn_id)
        .all()
    )
    amounts = [r[0] for r in rows]
    if len(amounts) < 3:
        return {"sufficient_history": False, "sample_size": len(amounts)}
    mean = statistics.mean(amounts)
    stdev = statistics.pstdev(amounts) or 1.0
    return {
        "sufficient_history": True,
        "sample_size": len(amounts),
        "mean_amount": round(mean, 2),
        "stdev_amount": round(stdev, 2),
    }


def tool_check_duplicate(db: Session, txn: Transaction) -> dict:
    window_start = txn.timestamp - timedelta(minutes=10)
    window_end = txn.timestamp + timedelta(minutes=10)
    dupes = (
        db.query(Transaction)
        .filter(
            Transaction.merchant_id == txn.merchant_id,
            Transaction.amount == txn.amount,
            Transaction.transaction_id != txn.transaction_id,
            Transaction.timestamp.between(window_start, window_end),
        )
        .count()
    )
    return {"possible_duplicates_in_10min_window": dupes}


def compute_zscore(amount: float, mean: float, stdev: float) -> float:
    return round((amount - mean) / stdev, 2) if stdev else 0.0


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an AI Finance Controller agent for a payments company.
You reconcile transactions against invoices and detect fraud/anomalies.

Rules you MUST follow:
- Base your verdict ONLY on the evidence provided below. Never assume facts not given.
- If invoice data is missing, reconciliation_status must be MISSING_INVOICE.
- If billed_amount differs from the transaction amount by more than 1%, it is MISMATCHED.
- If duplicates were found in the 10-minute window, flag is_anomaly=true and mention it.
- If the statistical z-score has |z| > {z_threshold}, flag is_anomaly=true.
- risk_score should reflect the SEVERITY of what you found (0 = fine, 100 = certain fraud).
- reasoning must cite the actual numbers you were given (amounts, z-score, duplicate count).
- Keep reasoning to 2-3 sentences.
Return your answer using the AgentVerdict tool/schema only.
"""


class ReconcileAgent:
    def __init__(self, db: Session):
        self.db = db
        self.chat_model = get_chat_model(temperature=0.0)
        self.structured_model = self.chat_model.with_structured_output(AgentVerdict)

    def _log(self, run_id: str, target_ref: str, step: str, detail: str):
        entry = AnalysisLog(run_id=run_id, target_type="transaction", target_ref=target_ref, step=step, detail=detail)
        self.db.add(entry)
        self.db.commit()

    def analyze_transaction(self, txn: Transaction, run_id: str) -> AgentVerdict:
        # --- Step 1: gather evidence via deterministic tools ---
        invoice_evidence = tool_get_invoice(self.db, txn.invoice_ref)
        self._log(run_id, txn.transaction_id, "tool_call:get_invoice", str(invoice_evidence))

        stats_evidence = tool_get_merchant_stats(self.db, txn.merchant_id, txn.transaction_id)
        self._log(run_id, txn.transaction_id, "tool_call:get_merchant_stats", str(stats_evidence))

        dup_evidence = tool_check_duplicate(self.db, txn)
        self._log(run_id, txn.transaction_id, "tool_call:check_duplicate", str(dup_evidence))

        zscore = None
        if stats_evidence.get("sufficient_history"):
            zscore = compute_zscore(txn.amount, stats_evidence["mean_amount"], stats_evidence["stdev_amount"])
        self._log(run_id, txn.transaction_id, "rule_engine:zscore", f"z={zscore}")

        # --- Step 2: build the evidence packet for the LLM ---
        evidence_prompt = f"""
Transaction under review:
  transaction_id: {txn.transaction_id}
  merchant_id: {txn.merchant_id}
  amount: {txn.amount} {txn.currency}
  status: {txn.status}
  payment_method: {txn.payment_method}
  timestamp: {txn.timestamp}
  invoice_ref: {txn.invoice_ref}

Invoice lookup result: {invoice_evidence}
Merchant historical stats: {stats_evidence}
Computed z-score for this amount vs merchant history: {zscore}
Duplicate check (10 min window, same merchant + amount): {dup_evidence}
Anomaly amount threshold configured: {settings.ANOMALY_AMOUNT_THRESHOLD}
Anomaly z-score threshold configured: {settings.ANOMALY_ZSCORE_THRESHOLD}
"""
        system = SYSTEM_PROMPT.format(z_threshold=settings.ANOMALY_ZSCORE_THRESHOLD)
        messages = build_messages(system, evidence_prompt)

        # --- Step 3: LLM verdict, schema-enforced ---
        verdict: AgentVerdict = call_with_retry(self.structured_model, messages)
        # Safety net: force the transaction_id field to match (models occasionally
        # normalize/typo IDs even under structured output).
        verdict.transaction_id = txn.transaction_id

        self._log(run_id, txn.transaction_id, "final_verdict", verdict.model_dump_json())

        # --- Step 4: persist verdict onto the transaction row ---
        txn.is_anomaly = verdict.is_anomaly
        txn.risk_score = verdict.risk_score
        txn.reconciliation_status = verdict.reconciliation_status
        txn.ai_reasoning = verdict.reasoning
        self.db.commit()

        return verdict

    def analyze_batch(self, transactions: list[Transaction]) -> tuple[str, list[AgentVerdict]]:
        run_id = str(uuid.uuid4())[:8]
        results = []
        for txn in transactions:
            try:
                results.append(self.analyze_transaction(txn, run_id))
            except Exception as e:
                self._log(run_id, txn.transaction_id, "error", str(e))
        return run_id, results
