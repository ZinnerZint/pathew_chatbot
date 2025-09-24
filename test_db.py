import psycopg2
import streamlit as st

cfg = st.secrets["postgres"]

try:
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode=cfg.get("sslmode", "require")
    )
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()

    st.success(f"✅ Connected to PostgreSQL: {version}")

    # ทดสอบดึงข้อมูลจากตาราง places
    cur.execute("SELECT * FROM places LIMIT 5;")
    rows = cur.fetchall()
    st.write("ตัวอย่างข้อมูลจากตาราง `places`:")
    st.dataframe(rows)

    cur.close()
    conn.close()

except Exception as e:
    st.error(f"❌ Error: {e}")
