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


def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
) -> Tuple[str, List[Dict]]:
    """
    ถ้ามีพิกัด → แนะนำเฉพาะ 'ใกล้ฉัน' (ภายใน 15 กม.)
    ถ้าไม่มีพิกัด → ค้นแบบเดิม (category/tambon/keywords)
    ส่งกลับ: (ข้อความสั้นๆ intro/outro, รายการสถานที่ dict สำหรับการ์ด)
    """
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon_pred = analysis.get("tambon")
    keywords = analysis.get("keywords")

    # ไม่เดาตำบลเอง ถ้าไม่ได้อยู่ในข้อความผู้ใช้
    tambon = _tambon_if_in_text(user_input, tambon_pred)

    # ----- ค้นหาข้อมูล -----
    if user_lat is not None and user_lng is not None:
        # ใกล้ฉันเท่านั้น
        results = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon, keywords=keywords,
            limit=10, within_km=15
        )
        intro = "เจอสถานที่ใกล้คุณครับ:"
    else:
        # ค้นแบบทั่วไป
        results = search_places(category=category, tambon=tambon, keywords=keywords, limit=10)
        intro = "เจอที่น่าสนใจให้ครับ:"

    # ----- กรองเพิ่มด้วย keywords แบบเข้ม (ถ้ามี) -----
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
            return ("ยังไม่พบสถานที่ใกล้คุณในรัศมี 15 กม. ครับ ลองระบุประเภทหรือคีย์เวิร์ดเพิ่มได้นะครับ", [])
        return ("ยังไม่พบสถานที่ที่ตรงกับคำค้นครับ ลองเพิ่มคีย์เวิร์ดหรือตำบล", [])

    outro = "หวังว่าจะมีสถานที่ตรงตามที่คุณต้องการนะครับ"
    # ไม่แนบรายละเอียดสถานที่ในข้อความ เพื่อไม่ซ้ำกับการ์ด
    return (f"{intro}\n\n{outro}", results)
