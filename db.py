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

def search_places(category=None, tambon=None, keywords_any=None, limit=30) -> List[Dict]:
    where_kw, p_kw = _build_keywords_or("kw", keywords_any)
    sql = f"""
    SELECT id, name, tambon, category, description, highlight,
           latitude, longitude, image_url,
           COALESCE(image_urls, '[]'::jsonb)::TEXT AS image_urls
    FROM places
    WHERE
      -- ยอมให้ category/tambon เป็นตัวกรองแบบหลวม (LIKE) และคีย์เวิร์ดช่วย OR
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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()

def search_places_nearby(lat, lng, category=None, tambon=None, keywords_any=None,
                         limit=30, within_km=20) -> List[Dict]:
    where_kw, p_kw = _build_keywords_or("kw", keywords_any)
    sql = f"""
    SELECT id, name, tambon, category, description, highlight,
           latitude, longitude, image_url,
           COALESCE(image_urls, '[]'::jsonb)::TEXT AS image_urls,
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
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()
