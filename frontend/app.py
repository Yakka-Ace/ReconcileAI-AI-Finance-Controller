"""
Streamlit frontend for ReconcileAI — AI Finance Controller.

Three tabs:
  1. Upload & Ingest    - CSV upload for transactions + invoices
  2. Run AI Analysis    - trigger the agent, watch live reasoning log
  3. Dashboard          - KPIs, charts, drill-down into any transaction's audit trail
"""
import os
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="ReconcileAI — AI Finance Controller", layout="wide", page_icon="💳")

st.title("💳 ReconcileAI — AI Finance Controller")
st.caption("Agentic invoice reconciliation & payment anomaly detection for fintech ledgers")

# --- health check / provider badge -----------------------------------------
try:
    health = requests.get(f"{BACKEND_URL}/health", timeout=5).json()
    provider = health.get("llm_provider", "none")
    if provider == "none":
        st.warning("⚠️ No LLM API key configured on the backend. Set one in `.env` before running analysis.")
    else:
        st.success(f"Backend connected — using **{provider.upper()}** as the reasoning engine.")
except Exception:
    st.error(f"Cannot reach backend at {BACKEND_URL}. Start it with `uvicorn main:app --reload` in /backend.")
    st.stop()

tab_upload, tab_analyze, tab_dashboard = st.tabs(["📤 Upload & Ingest", "🤖 Run AI Analysis", "📊 Dashboard"])

# =============================================================================
# TAB 1 — Upload
# =============================================================================
with tab_upload:
    st.subheader("Ingest transactions & invoices")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Transactions CSV**")
        st.caption("Required columns: transaction_id, merchant_id, amount, currency, status, payment_method, timestamp, invoice_ref")
        txn_file = st.file_uploader("Upload transactions.csv", type=["csv"], key="txn_upload")
        if txn_file is not None:
            csv_text = txn_file.getvalue().decode("utf-8")
            st.dataframe(pd.read_csv(pd.io.common.StringIO(csv_text)).head(5), use_container_width=True)
            if st.button("Ingest transactions", type="primary"):
                resp = requests.post(f"{BACKEND_URL}/ingest/transactions/csv", json={"csv_text": csv_text})
                if resp.ok:
                    st.success(resp.json())
                else:
                    st.error(resp.text)

    with col2:
        st.markdown("**Invoices CSV**")
        st.caption("Required columns: invoice_ref, merchant_id, billed_amount, currency, issue_date, due_date, status")
        inv_file = st.file_uploader("Upload invoices.csv", type=["csv"], key="inv_upload")
        if inv_file is not None:
            csv_text = inv_file.getvalue().decode("utf-8")
            st.dataframe(pd.read_csv(pd.io.common.StringIO(csv_text)).head(5), use_container_width=True)
            if st.button("Ingest invoices", type="primary"):
                resp = requests.post(f"{BACKEND_URL}/ingest/invoices/csv", json={"csv_text": csv_text})
                if resp.ok:
                    st.success(resp.json())
                else:
                    st.error(resp.text)

    st.divider()
    st.info(
        "No file handy? Generate a realistic sample ledger with "
        "`python scripts/generate_synthetic_data.py --n 500 --out data` — "
        "it seeds mismatches, missing invoices, duplicates, outliers, and refund-fraud loops."
    )

# =============================================================================
# TAB 2 — Run analysis
# =============================================================================
with tab_analyze:
    st.subheader("Trigger the reconciliation agent")
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        merchant_filter = st.text_input("Filter by merchant_id (optional)", "")
    with c2:
        batch_limit = st.number_input("Batch size", min_value=1, max_value=200, value=25)
    with c3:
        st.write("")
        st.write("")
        run_clicked = st.button("▶️ Run Analysis", type="primary")

    if run_clicked:
        payload = {"merchant_id": merchant_filter or None, "limit": int(batch_limit)}
        with st.spinner("Agent reasoning over transactions — calling tools, then the LLM..."):
            resp = requests.post(f"{BACKEND_URL}/analyze", json=payload, timeout=180)

        if resp.status_code == 404:
            st.info("No unreviewed transactions match this filter. Upload more data or widen the filter.")
        elif not resp.ok:
            st.error(resp.text)
        else:
            data = resp.json()
            st.success(f"Run `{data['run_id']}` complete — {len(data['results'])} transactions analyzed using **{data['provider_used'].upper()}**.")

            st.markdown("### 🧠 Live reasoning log")
            log_box = st.container(height=300)
            with log_box:
                for entry in data["log"]:
                    icon = "🔧" if "tool_call" in entry["step"] else ("📐" if "rule_engine" in entry["step"] else "✅")
                    st.text(f"{icon} [{entry['target']}] {entry['step']}: {entry['detail'][:180]}")

            st.markdown("### 📋 Verdicts")
            results_df = pd.DataFrame(data["results"])
            st.dataframe(results_df, use_container_width=True)

# =============================================================================
# TAB 3 — Dashboard
# =============================================================================
with tab_dashboard:
    st.subheader("Portfolio-level view")

    try:
        summary = requests.get(f"{BACKEND_URL}/stats/summary", timeout=10).json()
    except Exception as e:
        st.error(f"Could not load stats: {e}")
        summary = None

    if summary:
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Total Transactions", summary["total_transactions"])
        k2.metric("Reviewed", summary["reviewed"], delta=f"{summary['unreviewed']} pending")
        k3.metric("Anomalies Flagged", summary["anomalies_flagged"])
        k4.metric("Mismatched Invoices", summary["mismatched_invoices"])
        k5.metric("Avg Risk Score", summary["average_risk_score"])

    st.divider()

    col_filters, _ = st.columns([1, 3])
    with col_filters:
        anomalies_only = st.checkbox("Show anomalies only")
        status_filter = st.selectbox(
            "Reconciliation status", ["ALL", "MATCHED", "MISMATCHED", "MISSING_INVOICE", "DUPLICATE", "UNREVIEWED"]
        )

    params = {"limit": 500, "anomalies_only": anomalies_only}
    if status_filter != "ALL":
        params["status"] = status_filter

    txns = requests.get(f"{BACKEND_URL}/transactions", params=params, timeout=15).json()
    df = pd.DataFrame(txns)

    if df.empty:
        st.info("No transactions match this filter yet. Upload data and/or run analysis first.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            fig1 = px.pie(df, names="reconciliation_status", title="Reconciliation status breakdown")
            st.plotly_chart(fig1, use_container_width=True)
        with c2:
            risk_df = df[df["risk_score"] > 0]
            if not risk_df.empty:
                fig2 = px.histogram(risk_df, x="risk_score", nbins=20, title="Risk score distribution")
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No risk-scored transactions yet — run analysis first.")

        st.markdown("### Transaction ledger")
        st.dataframe(
            df[["transaction_id", "merchant_id", "amount", "status", "reconciliation_status", "is_anomaly", "risk_score"]],
            use_container_width=True,
            height=350,
        )

        st.markdown("### 🔍 Drill into a transaction's audit trail")
        selected_txn = st.selectbox("Select transaction_id", df["transaction_id"].tolist())
        if selected_txn:
            row = df[df["transaction_id"] == selected_txn].iloc[0]
            st.write(f"**AI reasoning:** {row.get('ai_reasoning') or '_not yet analyzed_'}")
            log_resp = requests.get(f"{BACKEND_URL}/transactions/{selected_txn}/logs", timeout=10)
            if log_resp.ok:
                for entry in log_resp.json():
                    st.text(f"[{entry['step']}] {entry['detail']}")
            else:
                st.caption("No detailed logs found — this transaction hasn't been analyzed yet.")
