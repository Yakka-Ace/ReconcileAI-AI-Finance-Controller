"""
SQLite persistence layer via SQLAlchemy.
Three tables: transactions (raw ledger), invoices (billed amounts),
and analysis_log (every agent run, for audit trail + reasoning history).
"""
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime, timezone

from config import settings

engine = create_engine(
    settings.DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    merchant_id = Column(String, index=True)
    amount = Column(Float)
    currency = Column(String, default="INR")
    status = Column(String)  # SUCCESS, FAILED, PENDING, REFUNDED
    payment_method = Column(String)
    timestamp = Column(DateTime)
    invoice_ref = Column(String, nullable=True, index=True)

    # populated after analysis
    is_anomaly = Column(Boolean, default=False)
    risk_score = Column(Float, default=0.0)
    reconciliation_status = Column(String, default="UNREVIEWED")  # MATCHED, MISMATCHED, MISSING, UNREVIEWED
    ai_reasoning = Column(Text, nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_ref = Column(String, unique=True, index=True)
    merchant_id = Column(String, index=True)
    billed_amount = Column(Float)
    currency = Column(String, default="INR")
    issue_date = Column(DateTime)
    due_date = Column(DateTime, nullable=True)
    status = Column(String, default="OPEN")  # OPEN, PAID, DISPUTED, VOID


class AnalysisLog(Base):
    __tablename__ = "analysis_log"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(String, index=True)
    target_type = Column(String)  # "transaction" | "batch"
    target_ref = Column(String, nullable=True)
    step = Column(String)  # e.g. "tool_call", "final_verdict"
    detail = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
