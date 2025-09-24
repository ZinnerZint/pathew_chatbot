import streamlit as st, psycopg2

cfg = st.secrets["postgres"]
try:
    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"], sslmode=cfg.get("sslmode","require")
    )
    with conn.cursor() as cur:
        cur.execute("SELECT version();")
        print("✅ Connected:", cur.fetchone()[0])
    conn.close()
except Exception as e:
    print("❌ Error:", e)
