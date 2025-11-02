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
    "ยิม": {"ฟิตเนส", "ฟิตเนสคลับ", "ฟิตเนสเซ็นเตอร์", "โรงยิม"},
    "ฟิตเนส": {"ยิม", "โรงยิม"},
    "โรงยิม": {"ยิม", "ฟิตเนส"},
    "คาเฟ่": {"กาแฟ", "คอฟฟี่", "coffee", "ร้านกาแฟ"},
    "กาแฟ": {"คาเฟ่", "คอฟฟี่", "ร้านกาแฟ"},
    "ปั๊มน้ำมัน": {"ปั๊ม", "PTT", "บางจาก", "เชลล์", "พีที"},
    "ปั๊ม": {"ปั๊มน้ำมัน", "PTT", "บางจาก", "เชลล์", "พีที"},
    "ตลาด": {"ตลาดนัด", "ตลาดสด", "มาร์เก็ต"},
}

# ---------- Helper ----------
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
    """รวมข้อความเก่าล่าสุดเป็นบริบท"""
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
    """ถ้าไม่ได้ระบุตำบลในรอบนี้ ลองใช้ตำบลจากบทสนทนาก่อนหน้า"""
    if not history_text:
        return None
    last_found = None
    for t in KNOWN_TAMBON:
        if t in history_text:
            last_found = t
    return last_found

def _tambon_if_in_text(user_input: str, predicted_tambon: Optional[str]) -> Optional[str]:
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

# ---------- Intent (ใช้ history เพื่อความต่อเนื่อง) ----------
def _understand(user_input: str, history_text: str) -> dict:
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นอำเภอปะทิว พูดธรรมชาติ สุภาพแบบเพื่อน "
        "ถ้าผู้ใช้ขอหาสถานที่ในปะทิว → want_search=true; "
        "ถ้าคุยทั่วไป → want_search=false. "
        "ใช้บริบทก่อนหน้าเพื่อเข้าใจความต่อเนื่องของบทสนทนา"
    )
    prompt = f"""{sys}

บริบทก่อนหน้า:
{history_text or "(ไม่มีประวัติ)"}

ตอบเป็น JSON:
{{
  "want_search": true|false,
  "category": null | "ประเภทสถานที่",
  "tambon": null | "ชื่อตำบลในปะทิว",
  "keywords": null | "คีย์เวิร์ดเพิ่ม",
  "tone_hint": "โทนการตอบ"
}}

ผู้ใช้: "{user_input}"
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
    prompt = (
        "บทบาท: เพื่อนผู้ช่วยท้องถิ่นปะทิว คุยสั้น เป็นกันเอง ไม่ยัดเยียดกลับไปหาสถานที่\n"
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"โทนที่ควรได้: {tone_hint}\n"
        f"ผู้ใช้: {user_input}\n"
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
    history: Optional[List[Dict]] = None,   # ใช้บทสนทนาเก่า
) -> Tuple[str, List[Dict]]:
    history_text = _history_to_text(history, max_turns=8)
    u = _understand(user_input, history_text)

    if not u.get("want_search"):
        return (_reply_chitchat(user_input, u.get("tone_hint", ""), history_text), [])

    category = u.get("category")
    tambon_now = _tambon_if_in_text(user_input, u.get("tambon"))
    tambon_hist = _infer_tambon_from_history(history_text)
    tambon = tambon_now or tambon_hist
    keywords_any = _expand_keywords_any(user_input, u.get("keywords"))

    if user_lat is not None and user_lng is not None:
        rows = search_places_nearby(
            user_lat, user_lng,
            category=category, tambon=tambon,
            keywords_any=keywords_any, limit=20, within_km=20
        )
    else:
        rows = search_places(category=category, tambon=tambon, keywords_any=keywords_any, limit=30)

    rows = _fuzzy_filter(rows, user_input, extra_terms=keywords_any, threshold=55, top_k=12)

    if not rows:
        return ("ขอโทษนะครับ เหมือนผมอาจจะเข้าใจคลาดเคลื่อนนิดหน่อย ลองช่วยถามใหม่อีกทีได้ไหมครับ", [])

    intro = "ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ใกล้เคียงกับความต้องการของคุณ"
    outro = "ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", rows)
