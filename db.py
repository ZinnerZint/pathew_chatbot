import psycopg2
import psycopg2.extras
import streamlit as st

def get_conn():
    cfg = st.secrets["postgres"]
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        dbname=cfg["dbname"],
        user=cfg["user"],
        password=cfg["password"],
        sslmode=cfg.get("sslmode", "require"),
    )

def search_places(category=None, tambon=None, limit=10):
    sql = """
    SELECT id, name, tambon, category, description, highlight,
           latitude, longitude, image_url
    FROM places
    WHERE (%(cat)s IS NULL OR category ILIKE %(cat_like)s)
      AND (%(tmb)s IS NULL OR tambon ILIKE %(tmb_like)s)
    ORDER BY name
    LIMIT %(lim)s;
    """
    params = {
        "cat": category,
        "tmb": tambon,
        "cat_like": f"%{category}%" if category else None,
        "tmb_like": f"%{tambon}%" if tambon else None,
        "lim": limit,
    }
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
