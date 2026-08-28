"""
Synthetic Data Generator for ReconcileAI.

Produces two CSVs (transactions.csv, invoices.csv) that mimic a
mid-size payments ledger, deliberately seeded with realistic
discrepancy patterns so the demo has something interesting to find:

  - Perfectly matched transactions (the majority — realism baseline)
  - Amount mismatches (transaction != invoice, e.g. partial refund not reflected)
  - Missing invoices (transaction with no matching invoice_ref)
  - Duplicate charges (same merchant/amount within minutes — double-billing bug)
  - Statistical outliers (one merchant suddenly charged 20x their usual ticket size)
  - Round-trip refund fraud pattern (rapid SUCCESS -> REFUNDED pairs)

Usage:
    python generate_synthetic_data.py --n 500 --out ../data
"""
import argparse
import random
import uuid
from datetime import datetime, timedelta
import pandas as pd

random.seed(42)

MERCHANTS = [f"MERCH{str(i).zfill(3)}" for i in range(1, 21)]
PAYMENT_METHODS = ["UPI", "CARD", "NETBANKING", "WALLET", "EMI"]
STATUSES = ["SUCCESS", "SUCCESS", "SUCCESS", "SUCCESS", "FAILED", "PENDING", "REFUNDED"]

# Each merchant has a "typical" ticket size so z-score anomalies are meaningful
MERCHANT_BASELINE = {m: random.uniform(500, 15000) for m in MERCHANTS}


def random_timestamp(days_back=30):
    return datetime.now() - timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def make_transaction(merchant_id, amount, ts, invoice_ref=None, status=None):
    return {
        "transaction_id": f"TXN{uuid.uuid4().hex[:10].upper()}",
        "merchant_id": merchant_id,
        "amount": round(amount, 2),
        "currency": "INR",
        "status": status or random.choice(STATUSES),
        "payment_method": random.choice(PAYMENT_METHODS),
        "timestamp": ts,
        "invoice_ref": invoice_ref,
    }


def make_invoice(invoice_ref, merchant_id, billed_amount, issue_date):
    return {
        "invoice_ref": invoice_ref,
        "merchant_id": merchant_id,
        "billed_amount": round(billed_amount, 2),
        "currency": "INR",
        "issue_date": issue_date,
        "due_date": issue_date + timedelta(days=15),
        "status": random.choice(["OPEN", "PAID", "PAID", "DISPUTED"]),
    }


def generate(n: int):
    transactions, invoices = [], []

    n_normal = int(n * 0.70)
    n_mismatch = int(n * 0.10)
    n_missing_invoice = int(n * 0.08)
    n_duplicate = int(n * 0.06)
    n_outlier = int(n * 0.04)
    n_refund_fraud = n - (n_normal + n_mismatch + n_missing_invoice + n_duplicate + n_outlier)

    # 1. Normal matched transactions
    for _ in range(n_normal):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        amount = max(50, random.gauss(base, base * 0.15))
        ts = random_timestamp()
        inv_ref = f"INV{uuid.uuid4().hex[:8].upper()}"
        transactions.append(make_transaction(merchant, amount, ts, inv_ref, status="SUCCESS"))
        invoices.append(make_invoice(inv_ref, merchant, amount, ts - timedelta(days=1)))

    # 2. Amount mismatches (invoice says one thing, transaction charged another)
    for _ in range(n_mismatch):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        billed = max(50, random.gauss(base, base * 0.1))
        charged = billed * random.choice([0.5, 0.75, 1.15, 1.3])  # partial refund or overcharge
        ts = random_timestamp()
        inv_ref = f"INV{uuid.uuid4().hex[:8].upper()}"
        transactions.append(make_transaction(merchant, charged, ts, inv_ref, status="SUCCESS"))
        invoices.append(make_invoice(inv_ref, merchant, billed, ts - timedelta(days=1)))

    # 3. Missing invoices
    for _ in range(n_missing_invoice):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        amount = max(50, random.gauss(base, base * 0.15))
        ts = random_timestamp()
        transactions.append(make_transaction(merchant, amount, ts, invoice_ref=None, status="SUCCESS"))

    # 4. Duplicate charges (double-billing bug simulation)
    for _ in range(n_duplicate // 2):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        amount = max(50, random.gauss(base, base * 0.1))
        ts = random_timestamp()
        inv_ref = f"INV{uuid.uuid4().hex[:8].upper()}"
        transactions.append(make_transaction(merchant, amount, ts, inv_ref, status="SUCCESS"))
        # duplicate fired 2-5 minutes later, no invoice of its own
        dup_ts = ts + timedelta(minutes=random.randint(2, 5))
        transactions.append(make_transaction(merchant, amount, dup_ts, invoice_ref=None, status="SUCCESS"))
        invoices.append(make_invoice(inv_ref, merchant, amount, ts - timedelta(days=1)))

    # 5. Statistical outliers (sudden huge charge vs merchant's normal ticket size)
    for _ in range(n_outlier):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        amount = base * random.uniform(15, 30)  # wildly outside normal range
        ts = random_timestamp()
        inv_ref = f"INV{uuid.uuid4().hex[:8].upper()}"
        transactions.append(make_transaction(merchant, amount, ts, inv_ref, status="SUCCESS"))
        invoices.append(make_invoice(inv_ref, merchant, amount, ts - timedelta(days=1)))

    # 6. Rapid refund round-trip pattern (potential card-testing / fraud loop)
    for _ in range(n_refund_fraud):
        merchant = random.choice(MERCHANTS)
        base = MERCHANT_BASELINE[merchant]
        amount = max(50, random.gauss(base * 0.3, 20))
        ts = random_timestamp()
        inv_ref = f"INV{uuid.uuid4().hex[:8].upper()}"
        transactions.append(make_transaction(merchant, amount, ts, inv_ref, status="SUCCESS"))
        transactions.append(
            make_transaction(merchant, amount, ts + timedelta(minutes=1), invoice_ref=None, status="REFUNDED")
        )
        invoices.append(make_invoice(inv_ref, merchant, amount, ts - timedelta(days=1)))

    random.shuffle(transactions)
    return pd.DataFrame(transactions), pd.DataFrame(invoices)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=500, help="approx number of transactions to generate")
    parser.add_argument("--out", type=str, default="../data", help="output directory")
    args = parser.parse_args()

    txns_df, inv_df = generate(args.n)
    txns_df.to_csv(f"{args.out}/transactions.csv", index=False)
    inv_df.to_csv(f"{args.out}/invoices.csv", index=False)

    print(f"Generated {len(txns_df)} transactions -> {args.out}/transactions.csv")
    print(f"Generated {len(inv_df)} invoices -> {args.out}/invoices.csv")
    print("Seeded discrepancy types: mismatches, missing invoices, duplicates, outliers, refund-fraud loops.")
