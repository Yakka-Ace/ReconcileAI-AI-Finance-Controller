# 🎬 Video Script — ReconcileAI (5-Minute Walkthrough)

Format: Loom/YouTube screen recording. Timestamps are targets, not hard cuts — pause naturally on-screen instead of rushing.

---

### [0:00 – 0:40] Problem (40 sec)

**On screen:** Title slide or README open in editor.

> "Hi, I'm Jashan, and this is ReconcileAI — an AI Finance Controller built for Razorpay's AI Builder Internship, Track 4.
>
> Here's the problem: every payments company deals with three recurring headaches at scale — transactions that don't match their invoices, transactions with no invoice at all, and anomalies like duplicate charges or sudden outlier amounts that could be fraud. Today this is either manual — slow and doesn't scale — or handled by rigid rule engines that can't explain *why* they flagged something.
>
> ReconcileAI fixes that by combining deterministic rule-checking with an LLM reasoning layer that explains every decision in plain English, backed by evidence."

---

### [0:40 – 2:40] Live Demo (2 min)

**On screen:** Streamlit app running.

> "Let's see it live. First tab: Upload & Ingest. I'll drop in a synthetic ledger of 500+ transactions and their invoices — this data was generated with a script that deliberately seeds six discrepancy types: matched transactions, amount mismatches, missing invoices, duplicate charges, statistical outliers, and refund-fraud loops."

*[Upload transactions.csv, upload invoices.csv, show the ingest confirmations]*

> "Now the second tab — Run AI Analysis. I'll trigger a batch of 25 transactions."

*[Click Run Analysis, let it process]*

> "Watch the live reasoning log on the left — for every transaction, you can see the agent calling its tools first: get_invoice, get_merchant_stats, check_duplicate, and computing a z-score — *before* it ever asks the LLM anything. Only once it has hard evidence does it hand that off to the model for a verdict."

*[Point at a MISMATCHED or anomaly result in the table]*

> "Here's one flagged MISMATCHED with a risk score of 62 — and the reasoning cites the actual invoice amount, the actual charged amount, and the z-score. This isn't a black box; every number in that explanation is traceable."

*[Switch to Dashboard tab]*

> "Third tab is the dashboard — KPIs across the whole ledger, a reconciliation status breakdown, risk score distribution, and if I drill into any single transaction, I get its full audit trail — every tool call, every intermediate number, and the final verdict. That's what makes this usable in an actual finance/compliance context."

---

### [2:40 – 3:50] Architecture (70 sec)

**On screen:** Mermaid diagram from the README.

> "Under the hood: FastAPI backend, SQLite ledger, Streamlit frontend. The core design decision is here — the agent never lets the LLM compute numbers or recall facts from memory. Deterministic Python tools do all the lookups and math: invoice matching, merchant statistics, duplicate detection, z-scores. All of that becomes an 'evidence packet' that's handed to the LLM.
>
> The LLM's only job is judgment: weigh the evidence, decide reconciliation status, anomaly flag, and risk score — and it has to return that through a strict schema, not free text, using LangChain's structured output bound to a Pydantic model. That's the single biggest hallucination-mitigation choice in this project.
>
> It's also provider-agnostic — OpenAI, Anthropic, or Gemini, whichever key you set — so it's not locked to one vendor."

---

### [3:50 – 4:35] Edge Cases (45 sec)

**On screen:** Back on the dashboard, showing different flagged types.

> "A few edge cases I specifically tested for: duplicate charges fired minutes apart get caught by the 10-minute window scan even with no shared invoice. Sudden outliers — a merchant whose typical ticket is a few thousand rupees suddenly charged 20x that — get caught by the z-score threshold even though each individual number looks 'valid' on its own. And rapid charge-then-refund pairs, a classic card-testing fraud pattern, get flagged as anomalies even though both transactions individually reconcile fine against their invoice.
>
> I also added retry logic with exponential backoff for API flakiness, and every ingestion endpoint deduplicates by transaction ID so re-uploading the same file twice is safe."

---

### [4:35 – 5:00] Future Scope & Close (25 sec)

**On screen:** README's "Future Scope" section.

> "Next steps: real-time streaming ingestion instead of CSV batch upload, PDF invoice parsing with OCR for unstructured merchant feeds, and a feedback loop where analyst overrides tune the rule thresholds automatically. Longer term, a second agent that drafts the actual merchant dispute email once a case is flagged.
>
> That's ReconcileAI — thanks for watching."

---

**Total runtime target: ~5:00.** Trim the demo section first if running long — the architecture explanation and the "why structured output matters" point are the parts a technical judge will care about most.
