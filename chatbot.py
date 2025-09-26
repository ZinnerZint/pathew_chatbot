import json
from typing import List, Dict, Tuple, Optional

import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ----- ตั้งค่า LLM -----
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

# รายชื่อตำบลในอำเภอปะทิว
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


def _format_history(history: Optional[list]) -> str:
    """แปลงประวัติแชทเป็นข้อความเรียบง่ายให้โมเดลอ่าน"""
    if not history:
        return ""
    lines = []
    for m in history[-8:]:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        speaker = "ผู้ใช้" if role == "user" else "บอท"
        text = (m.get("content") or "").strip()
        if text:
            lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def analyze_query(user_input: str, history: Optional[list] = None) -> dict:
    hist = _format_history(history)
    prompt = f"""
คุณคือระบบช่วยหาสถานที่ใน "อำเภอปะทิว" จังหวัดชุมพร เท่านั้น
หน้าที่: วิเคราะห์คำถามผู้ใช้แล้วสรุปเป็น JSON เท่านั้น ห้ามมีคำอธิบายอื่น
ห้ามแนะนำสถานที่นอกอำเภอปะทิว

บทสนทนาก่อนหน้า:
{hist if hist else "—"}

คำถามล่าสุดของผู้ใช้: "{user_input}"

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
    """รับเฉพาะตำบลที่ปรากฏจริงในข้อความ และต้องเป็นตำบลในอำเภอปะทิว"""
    if not predicted_tambon:
        return None
    ui = user_input.strip().lower()
    for t in KNOWN_TAMBON:
        if t in ui and predicted_tambon == t:
            return t
    return None


def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[list] = None,
) -> Tuple[str, List[Dict]]:
    """
    ใช้ LLM ช่วยเรียบเรียง แต่ข้อมูลสถานที่ต้องมาจาก DB เท่านั้น
    รองรับการถามต่อ: "กี่โล", "ใกล้มั้ย" โดยอิงจาก last_places
    """
    # ----- ตรวจสอบว่าผู้ใช้ถามเรื่องระยะทางต่อ -----
    ask_distance = any(kw in user_input for kw in ["กี่โล", "กี่กิโล", "ใกล้", "ไกล", "ระยะทาง"])
    if ask_distance and history:
        # หาผลลัพธ์ล่าสุดจาก history
        for h in reversed(history):
            if h.get("role") == "assistant" and h.get("last_places"):
                last_places = h["last_places"]
                if last_places:
                    first = last_places[0]
                    dist = first.get("distance_km")
                    if dist is not None:
                        km = round(float(dist), 1)
                        msg = f"{first['name']} อยู่ห่างจากคุณประมาณ {km} กม. หวังว่าจะเจอสถานที่ตรงตามที่คุณต้องการนะครับ"
                        return (msg, last_places)

    # ----- วิเคราะห์ query -----
    analysis = analyze_query(user_input, history=history)
    category = analysis.get("category")
    tambon_pred = analysis.get("tambon")
    keywords = analysis.get("keywords")

    tambon = _tambon_if_in_text(user_input, tambon_pred)

    # ----- ค้นหาข้อมูลจาก DB -----
    if user_lat is not None and user_lng is not None:
        results = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon, keywords=keywords,
            limit=5, within_km=15
        )
    else:
        results = search_places(category=category, tambon=tambon, keywords=keywords, limit=5)

    if not results:
        return ("ยังไม่พบสถานที่ที่ตรงกับคำค้นในอำเภอปะทิวครับ", [])

    # ----- เตรียมข้อมูลจริงจาก DB -----
    places_info = []
    for r in results:
        info = f"- {r['name']} (ประเภท: {r.get('category','')}, ตำบล {r.get('tambon','-')})"
        if r.get("distance_km"):
            info += f" ห่างจากคุณประมาณ {round(float(r['distance_km']),1)} กม."
        if r.get("highlight"):
            info += f" จุดเด่น: {r['highlight']}"
        places_info.append(info)

    context = "\n".join(places_info)

    # ----- ใช้ LLM เรียบเรียงคำตอบ -----
    prompt = f"""
คุณคือผู้ช่วย AI แนะนำสถานที่ใน "อำเภอปะทิว" จังหวัดชุมพร
***ข้อมูลข้อเท็จจริงที่คุณต้องใช้ มาจากรายการด้านล่างนี้เท่านั้น***
ห้ามสร้างข้อมูลใหม่ และต้องรายงาน "ระยะทาง (กม.)" ด้วยถ้ามี

คำถามของผู้ใช้: "{user_input}"

สถานที่ที่ค้นเจอ:
{context}

โปรดตอบกลับผู้ใช้อย่างสุภาพ สมูท และเป็นธรรมชาติ
ใช้เฉพาะข้อมูลจากรายการข้างต้น ห้ามแต่งเพิ่ม
ลงท้ายด้วย: "หวังว่าจะเจอสถานที่ตรงตามที่คุณต้องการนะครับ"
"""
    try:
        res = model.generate_content(prompt)
        reply = res.text.strip()
    except Exception:
        reply = "เจอสถานที่น่าสนใจให้ครับ หวังว่าจะเจอสถานที่ตรงตามที่คุณต้องการนะครับ"

    return (reply, results)
