import json
from typing import List, Dict, Tuple, Optional, Set

import google.generativeai as genai
from rapidfuzz import fuzz
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ตั้งค่าโมเดล
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)

# โฟกัสพื้นที่ปะทิว
KNOWN_TAMBON = {"ชุมโค", "บางสน", "ดอนยาง", "ปากคลอง", "ช้างแรก", "ทะเลทรัพย์", "เขาไชยราช"}

# คำพ้อง + คำนำหน้า
PREFIXES = ("โรง", "ร้าน", "ศูนย์", "สถาน", "ที่", "บ้าน")
SYNONYMS = {
    # ฟิตเนส/ยิม
    "ยิม": {"ฟิตเนส", "ฟิตเนสคลับ", "ฟิตเนสเซ็นเตอร์", "โรงยิม"},
    "ฟิตเนส": {"ยิม", "โรงยิม"},
    "โรงยิม": {"ยิม", "ฟิตเนส"},
    # คาเฟ่/กาแฟ
    "คาเฟ่": {"กาแฟ", "คอฟฟี่", "coffee", "ร้านกาแฟ"},
    "กาแฟ": {"คาเฟ่", "คอฟฟี่", "ร้านกาแฟ"},
    # ปั๊ม
    "ปั๊มน้ำมัน": {"ปั๊ม", "PTT", "บางจาก", "เชลล์", "พีที"},
    "ปั๊ม": {"ปั๊มน้ำมัน", "PTT", "บางจาก", "เชลล์", "พีที"},
    # ตลาด
    "ตลาด": {"ตลาดนัด", "ตลาดสด", "มาร์เก็ต"},
}

# ---------- Helpers ----------
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

def _history_to_text(history: Optional[List[Dict]], max_turns: int = 8) -> str:
    """
    แปลงประวัติแชทล่าสุดเป็นข้อความสั้น ๆ เพื่อให้โมเดลเข้าใจบริบท
    history: [{"role":"user"|"assistant","content": "..."}]
    """
    if not history:
        return ""
    lines = []
    for m in history[-max_turns:]:
        role = "ผู้ใช้" if m.get("role") == "user" else "AI"
        content = str(m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)

def _infer_tambon_from_history(history_text: str) -> Optional[str]:
    """ถ้าผู้ใช้ไม่ได้ระบุตำบลในรอบนี้ ลองดูจากบทสนทนาก่อนหน้า (เลือกอันที่ปรากฏล่าสุด)"""
    if not history_text:
        return None
    last_found = None
    for t in KNOWN_TAMBON:
        if t in history_text:
            last_found = t  # เก็บตัวที่เจอล่าสุดทับไปเรื่อย ๆ
    return last_found

def _tambon_if_in_text(user_input: str, predicted_tambon: Optional[str]) -> Optional[str]:
    """รับเฉพาะตำบลที่ปรากฏจริงในข้อความรอบนี้ (กัน LLM เดามั่ว)"""
    if not predicted_tambon:
        return None
    ui = user_input.strip().lower()
    for t in KNOWN_TAMBON:
        if t in ui and predicted_tambon == t:
            return t
    return None

def _normalize_terms(text: str) -> List[str]:
    toks = [t.strip() for t in text.replace(",", " ").split() if t.strip()]
    return toks if toks else ([text.strip()] if text.strip() else [])

def _expand_keywords_any(user_input: str, llm_keywords: Optional[str]) -> List[str]:
    """แตกคำ + ตัดคำนำหน้า + คำพ้อง → ใช้แบบ OR"""
    pool: Set[str] = set()
    def add(t: str):
        t = t.strip().lower()
        if not t:
            return
        pool.add(t)
        for p in PREFIXES:
            if t.startswith(p) and len(t) > len(p) + 1:
                pool.add(t[len(p):])
        if t in SYNONYMS:
            pool.update(x.lower() for x in SYNONYMS[t])
    for tk in _normalize_terms(user_input):
        add(tk)
    if llm_keywords and isinstance(llm_keywords, str):
        for tk in _normalize_terms(llm_keywords):
            add(tk)
    return [t for t in sorted(pool) if 1 <= len(t) <= 64]

def _fuzzy_filter(rows: List[Dict], query_text: str, extra_terms: Optional[List[str]] = None,
                  threshold: int = 55, top_k: int = 12) -> List[Dict]:
    """กันพิมพ์ผิดแบบเบา ๆ ด้วย partial_ratio; ใช้คะแนนสูงสุดของทุก term"""
    if not rows:
        return rows
    terms = []
    if query_text:
        terms.append(query_text)
    if extra_terms:
        terms.extend(extra_terms)
    def row_text(r):
        return " ".join([
            str(r.get("name") or ""),
            str(r.get("description") or ""),
            str(r.get("highlight") or ""),
            str(r.get("tambon") or ""),
            str(r.get("category") or ""),
        ]).lower()
    scored = []
    for r in rows:
        blob = row_text(r)
        score = max(fuzz.partial_ratio(t.lower(), blob) for t in terms if t.strip()) if terms else 0
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    filtered = [r for s, r in scored if s >= threshold]
    return filtered[:top_k] if filtered else [r for _, r in scored[:top_k]]

# ---------- ทำความเข้าใจเจตนา (รับ history) ----------
def _understand(user_input: str, history_text: str) -> dict:
    """
    - ถ้าผู้ใช้กำลังคุยเรื่องสถานที่ → want_search=true พร้อมพารามิเตอร์
    - ถ้าคุยทั่วไป → want_search=false (คุยเป็นธรรมชาติ)
    ใช้ history_text เพื่อให้โมเดลเข้าใจความต่อเนื่อง
    """
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นอำเภอปะทิว พูดธรรมชาติ สุภาพแบบเพื่อน "
        "โฟกัสเฉพาะอำเภอปะทิวเท่านั้น "
        "ถ้าผู้ใช้ขอหาสถานที่/แนะนำ ให้ตั้ง want_search=true; "
        "ถ้าเป็นการคุยทั่วไป ให้ตั้ง want_search=false. "
        "ใช้บริบทก่อนหน้าเพื่อคงความต่อเนื่องของหัวข้อสนทนา"
    )
    prompt = f"""{sys}

บริบทก่อนหน้า (ย่อ):
{history_text or "(ไม่มีประวัติ)"}

สรุปเป็น JSON เท่านั้น:
{{
  "want_search": true|false,
  "category": null | "ประเภทสถานที่",
  "tambon": null | "ชื่อตำบลในปะทิว",
  "keywords": null | "คีย์เวิร์ดเพิ่ม",
  "tone_hint": "โทนการตอบแบบสั้น ๆ"
}}

ผู้ใช้ (ล่าสุด): "{user_input}"
"""
    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text)
        return {
            "want_search": bool(data.get("want_search")),
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "keywords": data.get("keywords"),
            "tone_hint": data.get("tone_hint") or "",
        }
    except Exception:
        return {"want_search": False, "category": None, "tambon": None, "keywords": None, "tone_hint": ""}

def _reply_chitchat(user_input: str, tone_hint: str, history_text: str) -> str:
    """ตอบคุยเล่นสั้น ๆ ลื่น ๆ โดยคำนึงถึงบริบทก่อนหน้า"""
    prompt = (
        "บทบาท: เพื่อนผู้ช่วยท้องถิ่นปะทิว คุยสั้น เป็นกันเอง ไม่ยัดเยียดกลับไปหาสถานที่\n"
        f"บริบทก่อนหน้า (ย่อ):\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"โทนที่ควรได้: {tone_hint}\n"
        f"ผู้ใช้ (ล่าสุด): {user_input}\n"
        "ตอบ:"
    )
    try:
        res = model.generate_content(prompt)
        return (res.text or "").strip() or "ครับผม"
    except Exception:
        return "ครับผม"

# ---------- ฟังก์ชันหลัก ----------
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,   # ← รับประวัติแชทเข้ามา
) -> Tuple[str, List[Dict]]:
    """
    คืน (ข้อความตอบ, รายการสถานที่)
    - ไม่มีโหมดให้ผู้ใช้เห็น: ถ้าเขาคุย → คุย; ถ้าเขาขอหา → หา
    - ใช้ history เพื่อความต่อเนื่อง (จำหัวข้อ/ตำบลจากที่คุยกันก่อนหน้าได้)
    """
    history_text = _history_to_text(history, max_turns=8)

    u = _understand(user_input, history_text)

    # คุยทั่วไป → ตอบธรรมชาติ จบ
    if not u.get("want_search"):
        return (_reply_chitchat(user_input, u.get("tone_hint", ""), history_text), [])

    # หาในปะทิว → จัดพารามิเตอร์ค้นหา
    category = u.get("category")
    # ถ้ารอบนี้ไม่ระบุตำบล ลองใช้ของเดิมจากประวัติ (แต่ถ้ารอบนี้ระบุก็ใช้รอบนี้)
    tambon_now = _tambon_if_in_text(user_input, u.get("tambon"))
    tambon_hist = _infer_tambon_from_history(history_text)
    tambon = tambon_now or tambon_hist

    keywords_any = _expand_keywords_any(user_input, u.get("keywords"))

    # ค้นหา (ถ้ามีพิกัด → ใกล้ฉันก่อน)
    if user_lat is not None and user_lng is not None:
        rows = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon,
            keywords_any=keywords_any, limit=20, within_km=20
        )
    else:
        rows = search_places(category=category, tambon=tambon, keywords_any=keywords_any, limit=30)

    # กันพิมพ์ผิด + เรียงความใกล้เคียง
    rows = _fuzzy_filter(rows, user_input, extra_terms=keywords_any, threshold=55, top_k=12)

    if not rows:
        return ("ขอโทษนะครับ เหมือนผมอาจจะเข้าใจคลาดเคลื่อนนิดหน่อย ลองช่วยถามใหม่อีกทีได้ไหมครับ", [])

    # โทนเปิด-ปิดบทสนทนา (ไม่พูดถึงปักหมุด/งบ/เมนู)
    intro = "ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ใกล้เคียงกับความต้องการของคุณ"
    outro = "ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", rows)
