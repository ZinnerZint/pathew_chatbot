import json
from typing import List, Dict, Tuple, Optional
import google.generativeai as genai
from rapidfuzz import fuzz
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# -------------------------------
# ตั้งค่าโมเดล Gemini
# -------------------------------
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

# -------------------------------
# ตำบลในอำเภอปะทิว (กันหลุดพื้นที่)
# -------------------------------
KNOWN_TAMBON = {"ชุมโค", "บางสน", "ดอนยาง", "ปากคลอง", "ช้างแรก", "ทะเลทรัพย์", "เขาไชยราช"}

# -------------------------------
# Helper Functions
# -------------------------------
def _safe_json(text: str) -> dict:
    """กัน Gemini ตอบโค้ดบล็อก JSON"""
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

def _history_to_text(history: Optional[List[Dict]], max_turns: int = 8) -> str:
    """แปลงประวัติแชทเป็นข้อความสั้น ๆ ให้โมเดลเข้าใจบริบท"""
    if not history:
        return ""
    lines = []
    for m in history[-max_turns:]:
        role = "ผู้ใช้" if m.get("role") == "user" else "AI"
        content = str(m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)

def _fuzzy_filter(rows: List[Dict], query_text: str, threshold: int = 55, top_k: int = 12) -> List[Dict]:
    """จัดเรียงผลลัพธ์ตามความใกล้เคียงกับข้อความค้นหา"""
    if not rows:
        return []
    scored = []
    for r in rows:
        blob = " ".join([
            str(r.get("name") or ""),
            str(r.get("description") or ""),
            str(r.get("highlight") or ""),
            str(r.get("tambon") or ""),
            str(r.get("category") or ""),
        ]).lower()
        score = fuzz.partial_ratio(query_text.lower(), blob)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for s, r in scored if s >= threshold][:top_k]

# -------------------------------
# วิเคราะห์ความหมายประโยค (Prompt Intelligence)
# -------------------------------
def _understand(user_input: str, history_text: str) -> dict:
    """
    ใช้ Gemini วิเคราะห์ความหมายของประโยคโดยตรง
    เพื่อให้เข้าใจว่า ผู้ใช้ 'อยากหาอะไร' โดยไม่ต้องใช้ keyword mapping
    """
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นของอำเภอปะทิว จังหวัดชุมพร "
        "หน้าที่ของคุณคือวิเคราะห์สิ่งที่ผู้ใช้พูด แล้วบอกว่าผู้ใช้ต้องการค้นหาสถานที่หรือไม่ "
        "ถ้าต้องการ ให้ระบุประเภทสถานที่ (category) และตำบล (ถ้ามี) "
        "หากผู้ใช้คุยเรื่องทั่วไป ไม่ได้พูดถึงสถานที่ ให้ตั้ง want_search=false "
        "คุณตอบเฉพาะ JSON เท่านั้น ห้ามพูดเกิน"
    )

    examples = """
    ตัวอย่าง:
    ผู้ใช้: หิวข้าวจังเลย
    {"want_search": true, "category": "ร้านอาหาร", "tambon": null, "keywords": "อาหาร, ของกิน"}
    ผู้ใช้: อยากไปทะเล
    {"want_search": true, "category": "สถานที่ท่องเที่ยว", "tambon": null, "keywords": "ทะเล, ชายหาด"}
    ผู้ใช้: มีคาเฟ่แถวชุมโคไหม
    {"want_search": true, "category": "คาเฟ่", "tambon": "ชุมโค", "keywords": "กาแฟ, คาเฟ่"}
    ผู้ใช้: อยากไหว้พระ
    {"want_search": true, "category": "วัด", "tambon": null, "keywords": "วัด, ศาสนสถาน"}
    ผู้ใช้: ไม่มีอะไร แค่คุยเล่น
    {"want_search": false, "category": null, "tambon": null, "keywords": null}
    """

    prompt = f"""{sys}

บริบทก่อนหน้า:
{history_text or "(ไม่มีประวัติ)"}

{examples}

ผู้ใช้: "{user_input}"
ตอบเป็น JSON เท่านั้น:
"""

    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text)
        return {
            "want_search": bool(data.get("want_search")),
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "keywords": data.get("keywords"),
        }
    except Exception:
        return {"want_search": False, "category": None, "tambon": None, "keywords": None}

# -------------------------------
# ตอบคุยเล่น (โทนธรรมชาติ)
# -------------------------------
def _reply_chitchat(user_input: str, history_text: str) -> str:
    prompt = (
        "คุณคือเพื่อนผู้ช่วยท้องถิ่นของอำเภอปะทิว "
        "พูดคุยเป็นธรรมชาติ สุภาพแต่กันเอง "
        "อย่าเปลี่ยนเรื่องไปพูดถึงสถานที่ถ้าผู้ใช้ไม่ได้ถาม\n\n"
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"ผู้ใช้: {user_input}\n"
        "ตอบสั้น ๆ แบบอบอุ่น:"
    )
    try:
        res = model.generate_content(prompt)
        return (res.text or "").strip() or "ครับผม"
    except Exception:
        return "ครับผม"

# -------------------------------
# ฟังก์ชันหลักให้ app.py เรียกใช้
# -------------------------------
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,
) -> Tuple[str, List[Dict]]:
    """
    คืนผลลัพธ์ (ข้อความตอบ, รายการสถานที่)
    - ถ้าผู้ใช้คุยทั่วไป → คุยตอบ
    - ถ้าผู้ใช้พูดถึงสถานที่ → แนะนำสถานที่ในอำเภอปะทิว
    """
    history_text = _history_to_text(history, max_turns=8)
    u = _understand(user_input, history_text)

    # ถ้าไม่ใช่คำถามเกี่ยวกับสถานที่ → คุยตามน้ำ
    if not u.get("want_search"):
        return (_reply_chitchat(user_input, history_text), [])

    category = u.get("category")
    tambon = u.get("tambon")
    keywords_any = [kw.strip() for kw in (u.get("keywords") or "").split(",") if kw.strip()]

    # ------------------ ค้นหาสถานที่ ------------------
    if user_lat is not None and user_lng is not None:
        rows = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon,
            keywords_any=keywords_any, limit=20, within_km=20
        )
    else:
        rows = search_places(category=category, tambon=tambon, keywords_any=keywords_any, limit=30)

    rows = _fuzzy_filter(rows, user_input, threshold=55, top_k=12)

    # ------------------ ไม่มีผลลัพธ์ ------------------
    if not rows:
        return (
            "ขอโทษนะครับ เหมือนผมอาจจะเข้าใจคลาดเคลื่อนไปนิดหน่อย ลองช่วยถามใหม่อีกทีได้ไหมครับ",
            []
        )

    # ------------------ มีผลลัพธ์ ------------------
    intro = "ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ใกล้เคียงกับความต้องการของคุณ"
    outro = "ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", rows)
