"""
Pydantic schemas. These double as the JSON-schema contract we force
the LLM to answer in (see agent.py) — this is the main hallucination
mitigation: the model cannot return free text, only a validated object.
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime


class TransactionIn(BaseModel):
    transaction_id: str
    merchant_id: str
    amount: float
    currency: str = "INR"
    status: str
    payment_method: str
    timestamp: datetime
    invoice_ref: Optional[str] = None


class InvoiceIn(BaseModel):
    invoice_ref: str
    merchant_id: str
    billed_amount: float
    currency: str = "INR"
    issue_date: datetime
    due_date: Optional[datetime] = None
    status: str = "OPEN"


class TransactionOut(TransactionIn):
    id: int
    is_anomaly: bool
    risk_score: float
    reconciliation_status: str
    ai_reasoning: Optional[str] = None

    class Config:
        from_attributes = True


class AgentVerdict(BaseModel):
    """
    The strict JSON contract the LLM MUST return for every transaction
    it reasons about. Enforced via function/tool-calling schema so the
    model cannot free-text an answer.
    """
    transaction_id: str
    reconciliation_status: Literal["MATCHED", "MISMATCHED", "MISSING_INVOICE", "DUPLICATE"]
    is_anomaly: bool
    risk_score: float = Field(ge=0, le=100, description="0 = no risk, 100 = certain fraud/error")
    reasoning: str = Field(description="Short, evidence-based explanation citing the specific numbers/tools used")
    recommended_action: str


class CsvPayload(BaseModel):
    csv_text: str


class AnalyzeRequest(BaseModel):
    merchant_id: Optional[str] = None
    limit: int = 25


class AnalyzeResponse(BaseModel):
    run_id: str
    provider_used: str
    results: list[AgentVerdict]
    log: list[dict]
