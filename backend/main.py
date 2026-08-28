"""
FastAPI backend for the AI Finance Controller.

Endpoints:
  POST /ingest/transactions   - bulk upload transactions (CSV parsed client-side or JSON)
  POST /ingest/invoices       - bulk upload invoices
  POST /analyze               - run the ReconcileAgent over unreviewed transactions
  GET  /transactions          - list/filter transactions (for the dashboard)
  GET  /transactions/{id}/logs - full reasoning trace for one transaction
  GET  /stats/summary         - aggregate KPIs for the dashboard
  GET  /health                - liveness + which LLM provider is active
"""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
import pandas as pd
import io

from database import init_db, get_db, Transaction, Invoice, AnalysisLog
from schemas import TransactionIn, InvoiceIn, TransactionOut, AnalyzeRequest, AnalyzeResponse, CsvPayload
from agent import ReconcileAgent
from config import settings

app = FastAPI(
    title="AI Finance Controller — ReconcileAI",
    description="Agentic invoice reconciliation & payment anomaly detection for fintech ledgers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "llm_provider": settings.active_provider()}


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

@app.post("/ingest/transactions")
def ingest_transactions(rows: list[TransactionIn], db: Session = Depends(get_db)):
    inserted, skipped = 0, 0
    for row in rows:
        exists = db.query(Transaction).filter(Transaction.transaction_id == row.transaction_id).first()
        if exists:
            skipped += 1
            continue
        db.add(Transaction(**row.model_dump()))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped_duplicates": skipped}


@app.post("/ingest/transactions/csv")
def ingest_transactions_csv(payload: CsvPayload, db: Session = Depends(get_db)):
    """Accepts raw CSV text in the request body (used by the Streamlit uploader).
    Sent as a JSON body rather than a query param since real ledgers can be
    tens of thousands of rows — well past typical URL length limits."""
    df = pd.read_csv(io.StringIO(payload.csv_text), parse_dates=["timestamp"])
    inserted, skipped = 0, 0
    for _, row in df.iterrows():
        if db.query(Transaction).filter(Transaction.transaction_id == row["transaction_id"]).first():
            skipped += 1
            continue
        db.add(Transaction(
            transaction_id=row["transaction_id"],
            merchant_id=row["merchant_id"],
            amount=float(row["amount"]),
            currency=row.get("currency", "INR"),
            status=row["status"],
            payment_method=row["payment_method"],
            timestamp=row["timestamp"],
            invoice_ref=row.get("invoice_ref") if pd.notna(row.get("invoice_ref")) else None,
        ))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped_duplicates": skipped}


@app.post("/ingest/invoices/csv")
def ingest_invoices_csv(payload: CsvPayload, db: Session = Depends(get_db)):
    df = pd.read_csv(io.StringIO(payload.csv_text), parse_dates=["issue_date", "due_date"])
    inserted, skipped = 0, 0
    for _, row in df.iterrows():
        if db.query(Invoice).filter(Invoice.invoice_ref == row["invoice_ref"]).first():
            skipped += 1
            continue
        db.add(Invoice(
            invoice_ref=row["invoice_ref"],
            merchant_id=row["merchant_id"],
            billed_amount=float(row["billed_amount"]),
            currency=row.get("currency", "INR"),
            issue_date=row["issue_date"],
            due_date=row.get("due_date"),
            status=row.get("status", "OPEN"),
        ))
        inserted += 1
    db.commit()
    return {"inserted": inserted, "skipped_duplicates": skipped}


# ---------------------------------------------------------------------------
# Analysis (the agentic core)
# ---------------------------------------------------------------------------

@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, db: Session = Depends(get_db)):
    query = db.query(Transaction).filter(Transaction.reconciliation_status == "UNREVIEWED")
    if req.merchant_id:
        query = query.filter(Transaction.merchant_id == req.merchant_id)
    transactions = query.limit(req.limit).all()

    if not transactions:
        raise HTTPException(status_code=404, detail="No unreviewed transactions found for the given filter.")

    agent = ReconcileAgent(db)
    run_id, results = agent.analyze_batch(transactions)

    log_rows = (
        db.query(AnalysisLog)
        .filter(AnalysisLog.run_id == run_id)
        .order_by(AnalysisLog.id.asc())
        .all()
    )
    log = [{"step": r.step, "target": r.target_ref, "detail": r.detail} for r in log_rows]

    return AnalyzeResponse(run_id=run_id, provider_used=settings.active_provider(), results=results, log=log)


# ---------------------------------------------------------------------------
# Read / dashboard endpoints
# ---------------------------------------------------------------------------

@app.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    merchant_id: Optional[str] = None,
    anomalies_only: bool = False,
    status: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
):
    query = db.query(Transaction)
    if merchant_id:
        query = query.filter(Transaction.merchant_id == merchant_id)
    if anomalies_only:
        query = query.filter(Transaction.is_anomaly == True)  # noqa: E712
    if status:
        query = query.filter(Transaction.reconciliation_status == status)
    return query.order_by(Transaction.timestamp.desc()).limit(limit).all()


@app.get("/transactions/{transaction_id}/logs")
def transaction_logs(transaction_id: str, db: Session = Depends(get_db)):
    logs = (
        db.query(AnalysisLog)
        .filter(AnalysisLog.target_ref == transaction_id)
        .order_by(AnalysisLog.id.asc())
        .all()
    )
    if not logs:
        raise HTTPException(status_code=404, detail="No analysis logs for this transaction yet.")
    return [{"step": l.step, "detail": l.detail, "created_at": l.created_at} for l in logs]


@app.get("/stats/summary")
def stats_summary(db: Session = Depends(get_db)):
    total = db.query(func.count(Transaction.id)).scalar() or 0
    reviewed = db.query(func.count(Transaction.id)).filter(Transaction.reconciliation_status != "UNREVIEWED").scalar() or 0
    anomalies = db.query(func.count(Transaction.id)).filter(Transaction.is_anomaly == True).scalar() or 0  # noqa: E712
    mismatched = db.query(func.count(Transaction.id)).filter(Transaction.reconciliation_status == "MISMATCHED").scalar() or 0
    missing_invoice = db.query(func.count(Transaction.id)).filter(Transaction.reconciliation_status == "MISSING_INVOICE").scalar() or 0
    total_value = db.query(func.sum(Transaction.amount)).scalar() or 0
    avg_risk = db.query(func.avg(Transaction.risk_score)).scalar() or 0

    return {
        "total_transactions": total,
        "reviewed": reviewed,
        "unreviewed": total - reviewed,
        "anomalies_flagged": anomalies,
        "mismatched_invoices": mismatched,
        "missing_invoices": missing_invoice,
        "total_transaction_value": round(total_value, 2),
        "average_risk_score": round(avg_risk, 2),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
