import json
from typing import List, Dict, Tuple, Optional

import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ----- ตั้งค่า LLM -----
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

# รายชื่อตำบลในอำเภอปะทิว (ปรับ/เพิ่มได้)
KNOWN_TAMBON = {"ชุมโค", "บางสน", "ดอนยาง", "ปากคลอง", "ช้างแรก", "ทะเลทรัพย์", "เขาไชยราช"}

def _safe_json(text: str) -> dict:
    if not text:
        return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = "\n".join(t.split("\n")[1:])
    try:
        return json.loads(t)
    except Exception:
        return {}

def analyze_query(user_input: str) -> dict:
    prompt = f"""
คุณคือระบบช่วยหาสถานที่ใน "อำเภอปะทิว" จังหวัดชุมพร เท่านั้น
หน้าที่: วิเคราะห์คำถามผู้ใช้แล้วสรุปเป็น JSON เท่านั้น ห้ามมีคำอธิบายอื่น
ห้ามเดาตำบลถ้าผู้ใช้ไม่ได้ระบุในข้อความ

ผู้ใช้: "{user_input}"

จงตอบเป็น JSON โครงสร้างนี้เท่านั้น:
{{
  "category": "ประเภทสถานที่ เช่น ร้านอาหาร/คาเฟ่/ปั๊มน้ำมัน (ไม่รู้ให้ใส่ null)",
  "tambon": "ชื่อตำบลในอำเภอปะทิว (ไม่รู้ให้ใส่ null)",
  "price": "ถูก/ปานกลาง/แพง (ถ้ามี ไม่รู้ให้ใส่ null)",
  "keywords": "คำค้นเพิ่ม เช่น ชื่อสถานที่ เมนู หรือบรรยากาศ (ไม่มีให้ใส่ null)"
}}
"""
    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text)
        return {
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "price": data.get("price"),
            "keywords": data.get("keywords"),
        }
    except Exception:
        return {"category": None, "tambon": None, "price": None, "keywords": None}

def _format_one_place(p: Dict) -> str:
    name = p.get("name") or "-"
    tambon = p.get("tambon") or "-"
    cat = p.get("category") or ""
    desc = (p.get("description") or "").strip()
    hi = (p.get("highlight") or "").strip()
    lat = p.get("latitude")
    lng = p.get("longitude")

    lines = [f"• {name} ({cat}) – ตำบล{tambon}"]
    if desc:
        lines.append(desc)
    if hi:
        lines.append(f"จุดเด่น: {hi}")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        map_link = f"https://www.google.com/maps?q={lat},{lng}"
        lines.append(f"🗺️ พิกัด: {lat:.6f}, {lng:.6f}  |  [เปิดแผนที่]({map_link})")
    return "\n".join(lines)

def _tambon_if_in_text(user_input: str, predicted_tambon: Optional[str]) -> Optional[str]:
    """
    รับเฉพาะตำบลที่ 'ปรากฏจริง' ในข้อความผู้ใช้ และต้องเป็นตำบลในอำเภอปะทิว
    """
    if not predicted_tambon:
        return None
    ui = user_input.strip().lower()
    for t in KNOWN_TAMBON:
        if t in ui and predicted_tambon == t:
            return t
    return None  # ไม่เจอในข้อความผู้ใช้ → ตัดเดาทิ้ง

def get_answer(user_input: str, user_lat: Optional[float] = None, user_lng: Optional[float] = None) -> Tuple[str, List[Dict]]:
    """
    ถ้ามีพิกัด → แนะนำเฉพาะ 'ใกล้ฉัน'
    ถ้าไม่มีพิกัด → ค้นแบบเดิม
    """
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon_pred = analysis.get("tambon")
    keywords = analysis.get("keywords")

    tambon = _tambon_if_in_text(user_input, tambon_pred)

    results: List[Dict] = []

    # ✅ ถ้ามีพิกัด ให้ใช้ near-by เท่านั้น (แนะนำเฉพาะที่ใกล้ ๆ)
    if user_lat is not None and user_lng is not None:
        results = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon, keywords=keywords,
            limit=10, within_km=15
        )
        intro = "เจอสถานที่ใกล้คุณครับ:\n\n"
    else:
        # ไม่มีพิกัด → ค้นแบบทั่วไป
        results = search_places(category=category, tambon=tambon, keywords=keywords, limit=10)
        intro = "เจอที่น่าสนใจให้ครับ:\n\n"

    # เข้มงวดด้วย keywords อีกชั้น (ถ้ามี)
    if keywords and isinstance(keywords, str):
        kw = [k.strip().lower() for k in keywords.split() if k.strip()]
        if kw:
            def ok(row):
                text = " ".join([
                    str(row.get("name") or ""),
                    str(row.get("description") or ""),
                    str(row.get("highlight") or ""),
                ]).lower()
                return all(k in text for k in kw)
            filtered = list(filter(ok, results))
            if filtered:
                results = filtered

    if not results:
        if user_lat is not None and user_lng is not None:
            return ("ยังไม่พบสถานที่ใกล้คุณในรัศมี 15 กม. ครับ ลองขยายรัศมีหรือระบุประเภท/คีย์เวิร์ดเพิ่มได้ครับ", [])
        return ("ยังไม่พบสถานที่ที่ตรงกับคำค้นครับ ลองเพิ่มคีย์เวิร์ดหรือตำบล", [])

    body = "\n\n".join(_format_one_place(p) for p in results)
    return (intro + body, results)
