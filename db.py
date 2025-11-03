# db.py — robust version (ทนต่อคอลัมน์ที่ไม่มีในตาราง เช่น image_urls, id)
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

def _build_keywords_or(prefix: str, keywords_any: Optional[List[str]]):
    """สร้างเงื่อนไข OR สำหรับคีย์เวิร์ดหลายคำ (match หลายคอลัมน์)"""
    if not keywords_any:
        return "TRUE", {}
    clauses, params = [], {}
    for i, term in enumerate(keywords_any):
        key = f"{prefix}{i}"
        params[key] = f"%{term}%"
        clauses.append(
            "("
            "name ILIKE %({k})s OR "
            "description ILIKE %({k})s OR "
            "highlight ILIKE %({k})s OR "
            "category ILIKE %({k})s OR "
            "tambon ILIKE %({k})s"
            ")".format(k=key)
        )
    return "(" + " OR ".join(clauses) + ")", params

def _select_fields(conn):
    """กำหนดฟิลด์ที่จะ SELECT ตามคอลัมน์ที่มีจริงในตาราง"""
    has_id = _has_column(conn, "places", "id")
    has_image_urls = _has_column(conn, "places", "image_urls")

    fields = [
        "name", "tambon", "category", "description", "highlight",
        "latitude", "longitude", "image_url"
    ]
    if has_id:
        fields.insert(0, "id")

    # image_urls อาจไม่มี → สร้างเป็น [] แทน
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
          (%(cat)s IS NULL OR category ILIKE %(cat_like)s OR name ILIKE %(cat_like)s)
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
          AND (%(cat)s IS NULL OR category ILIKE %(cat_like)s OR name ILIKE %(cat_like)s)
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
            "lat": lat, "lng": lng,
            "cat": category, "tmb": tambon,
            "cat_like": f"%{category}%" if category else None,
            "tmb_like": f"%{tambon}%" if tambon else None,
            "within": within_km, "lim": limit,
        }
        params.update(p_kw)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
