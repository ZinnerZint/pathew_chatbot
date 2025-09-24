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

def search_places(category=None, tambon=None, keywords=None, limit=10):
    """
    ค้นแบบทั่วไป (ไม่ใช้พิกัด)
    """
    sql = """
    SELECT id, name, tambon, category, description, highlight,
           latitude, longitude, image_url,
           COALESCE(image_urls, '[]'::jsonb)::TEXT AS image_urls
    FROM places
    WHERE (%(cat)s IS NULL OR category ILIKE %(cat_like)s)
      AND (%(tmb)s IS NULL OR tambon ILIKE %(tmb_like)s)
      AND (%(kw)s IS NULL OR (
            name ILIKE %(kw_like)s
         OR description ILIKE %(kw_like)s
         OR highlight ILIKE %(kw_like)s
      ))
    ORDER BY name
    LIMIT %(lim)s;
    """
    params = {
        "cat": category,
        "tmb": tambon,
        "kw": keywords,
        "cat_like": f"%{category}%" if category else None,
        "tmb_like": f"%{tambon}%" if tambon else None,
        "kw_like": f"%{keywords}%" if keywords else None,
        "lim": limit,
    }
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()

def search_places_nearby(lat, lng, category=None, tambon=None, keywords=None, limit=10, within_km=15):
    """
    ค้นเฉพาะสถานที่ 'ใกล้ฉัน' โดยใช้ Haversine (ระยะทางหน่วยกม.)
    """
    sql = """
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
      AND (%(cat)s IS NULL OR category ILIKE %(cat_like)s)
      AND (%(tmb)s IS NULL OR tambon ILIKE %(tmb_like)s)
      AND (%(kw)s IS NULL OR (
            name ILIKE %(kw_like)s
         OR description ILIKE %(kw_like)s
         OR highlight ILIKE %(kw_like)s
      ))
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
        "cat": category,
        "tmb": tambon,
        "kw": keywords,
        "cat_like": f"%{category}%" if category else None,
        "tmb_like": f"%{tambon}%" if tambon else None,
        "kw_like": f"%{keywords}%" if keywords else None,
        "within": within_km,
        "lim": limit,
    }
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return cur.fetchall()
