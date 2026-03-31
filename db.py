import psycopg2
import psycopg2.extras
import streamlit as st
from typing import List, Dict, Optional


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


def _has_column(conn, table: str, column: str) -> bool:
    q = """
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = %s
      AND column_name = %s
    LIMIT 1;
    """
    with conn.cursor() as cur:
        cur.execute(q, (table, column))
        return cur.fetchone() is not None


def _norm_text(value: str) -> str:
    if not value:
        return ""
    return (
        value.strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
    )


def _norm_sql(expr: str) -> str:
    return f"LOWER(REPLACE(REPLACE(REPLACE(COALESCE({expr}, ''), ' ', ''), '-', ''), '_', ''))"


def _build_keywords_or(prefix: str, keywords_any: Optional[List[str]]):
    """
    ค้นทั้งแบบปกติ และแบบตัดช่องว่าง/ขีด/underscore
    เพื่อให้พิมพ์ติดกันหรือไม่มีวรรคยังหาเจอ
    """
    if not keywords_any:
        return "TRUE", {}

    clauses = []
    params = {}

    searchable_cols = ["name", "description", "highlight", "category", "tambon"]

    for i, term in enumerate(keywords_any):
        raw_term = (term or "").strip()
        norm_term = _norm_text(raw_term)
        if not raw_term:
            continue

        raw_key = f"{prefix}{i}"
        norm_key = f"{prefix}{i}_norm"

        params[raw_key] = f"%{raw_term}%"
        params[norm_key] = f"%{norm_term}%"

        col_parts = []
        for col in searchable_cols:
            col_parts.append(f"{col} ILIKE %({raw_key})s")
            col_parts.append(f"{_norm_sql(col)} LIKE %({norm_key})s")

        clauses.append("(" + " OR ".join(col_parts) + ")")

    if not clauses:
        return "TRUE", {}

    return "(" + " OR ".join(clauses) + ")", params


def _select_fields(conn):
    has_id = _has_column(conn, "places", "id")
    has_image_urls = _has_column(conn, "places", "image_urls")

    fields = [
        "name", "tambon", "category", "description", "highlight",
        "latitude", "longitude", "image_url"
    ]
    if has_id:
        fields.insert(0, "id")

    if has_image_urls:
        fields.append("COALESCE(image_urls, '[]'::jsonb)::TEXT AS image_urls")
    else:
        fields.append("'[]'::TEXT AS image_urls")

    return ", ".join(fields)


def search_places(category=None, tambon=None, keywords_any=None, limit=30) -> List[Dict]:
    with get_conn() as conn:
        select_fields = _select_fields(conn)
        where_kw, p_kw = _build_keywords_or("kw", keywords_any)

        sql = f"""
        SELECT {select_fields}
        FROM places
        WHERE
          (%(cat)s IS NULL OR category ILIKE %(cat_like)s)
          AND (%(tmb)s IS NULL OR tambon ILIKE %(tmb_like)s)
          AND {where_kw}
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
        params.update(p_kw)

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def search_places_nearby(lat, lng, category=None, tambon=None, keywords_any=None,
                         limit=30, within_km=20) -> List[Dict]:
    with get_conn() as conn:
        select_fields = _select_fields(conn)
        where_kw, p_kw = _build_keywords_or("kw", keywords_any)

        sql = f"""
        SELECT
           {select_fields},
           6371 * acos(
               cos(radians(%(lat)s)) * cos(radians(latitude)) *
               cos(radians(longitude) - radians(%(lng)s)) +
               sin(radians(%(lat)s)) * sin(radians(latitude))
           ) AS distance_km
        FROM places
        WHERE (latitude IS NOT NULL AND longitude IS NOT NULL)
          AND (%(cat)s IS NULL OR category ILIKE %(cat_like)s)
          AND (%(tmb)s IS NULL OR tambon ILIKE %(tmb_like)s)
          AND {where_kw}
          AND (
              6371 * acos(
                   cos(radians(%(lat)s)) * cos(radians(latitude)) *
                   cos(radians(longitude) - radians(%(lng)s)) +
                   sin(radians(%(lat)s)) * sin(radians(latitude))
              )
          ) <= %(within)s
        ORDER BY distance_km ASC
        LIMIT %(lim)s;
        """

        params = {
            "lat": lat,
            "lng": lng,
            "cat": category,
            "tmb": tambon,
            "cat_like": f"%{category}%" if category else None,
            "tmb_like": f"%{tambon}%" if tambon else None,
            "within": within_km,
            "lim": limit,
        }
        params.update(p_kw)

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()