import json
import re
from typing import List, Dict, Tuple, Optional
import google.generativeai as genai
from rapidfuzz import fuzz
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ---------- ตั้งค่าโมเดล ----------
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(
    MODEL_NAME,
    generation_config={
        "max_output_tokens": 500,
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
    }
)

KNOWN_TAMBON = {"ชุมโค", "บางสน", "ดอนยาง", "ปากคลอง", "ช้างแรก", "ทะเลทรัพย์", "เขาไชยราช"}

# ===== Helpers =====
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
    if not history:
        return ""
    lines = []
    for m in history[-max_turns:]:
        role = "ผู้ใช้" if m.get("role") == "user" else "AI"
        c = str(m.get("content") or "").strip()
        if c:
            lines.append(f"{role}: {c}")
    return "\n".join(lines)

def _norm(s: str) -> str:
    return (s or "").strip().lower()

STOP_WORDS = {
    "อยาก", "ช่วย", "หน่อย", "แถว", "ที่", "มี", "ไหม", "มั้ย", "ครับ", "ค่ะ",
    "คับ", "จ้า", "นะ", "บ้าง", "ขอ", "หา", "ด้วย", "เอา", "หนึ่ง", "นึง", "แนะนำ",
    "ตรง", "แถวไหน", "ขอหน่อย"
}

# เดาในเครื่อง (กันพลาด) ครอบคลุมเคสที่เจอบ่อย
LOCAL_CATEGORY_HINTS = {
    "ยิม/ฟิตเนส": {"ยิม", "ฟิตเนส", "ออกกำลัง", "เวท", "ฟิตเนต"},
    "ร้านซ่อมรถ": {"อู่", "ซ่อมรถ", "ศูนย์", "ร้านยาง", "ปะยาง", "แบตเตอรี่", "แม็ก", "ช่วงล่าง"},
    "ร้านอาหาร": {"กินข้าว", "ข้าว", "กับข้าว", "อาหาร", "หิว"},
    "คาเฟ่": {"คาเฟ่", "กาแฟ", "ชานม", "ชาเย็น", "ชา", "นั่งชิล"},
    "ตลาด": {"ตลาด", "ตลาดสด", "ตลาดนัด"},
    "วัด": {"ไหว้พระ", "วัด", "ทำบุญ"},
    "ปั๊มน้ำมัน": {"ปั๊ม", "เติมน้ำมัน", "ปั๊มน้ำมัน", "ptt", "บางจาก", "เชลล์", "พีที"},
    "ที่พัก": {"ที่พัก", "รีสอร์ท", "โฮมสเตย์", "โรงแรม"},
    "สถานที่ท่องเที่ยว": {"เที่ยว", "ทะเล", "ชายหาด", "จุดชมวิว", "แลนด์มาร์ก"},
}

def _local_guess_category(user_input: str) -> Optional[str]:
    txt = _norm(user_input)
    for cat, words in LOCAL_CATEGORY_HINTS.items():
        if any(w in txt for w in words):
            return cat
    return None

def _extract_keywords(user_input: str, llm_keywords: Optional[str]) -> List[str]:
    pool = set()
    raw = _norm(user_input).replace(",", " ")
    for tok in raw.split():
        if len(tok) >= 2 and tok not in STOP_WORDS:
            pool.add(tok)
    if llm_keywords:
        for tok in _norm(llm_keywords).replace(",", " ").split():
            if len(tok) >= 2 and tok not in STOP_WORDS:
                pool.add(tok)
    return sorted(pool)

def _rank(rows: List[Dict], query_text: str, prefer_category: Optional[str],
          prefer_tambon: Optional[str], top_k: int = 12) -> List[Dict]:
    """เรียงคะแนน: fuzzy + โบนัส category/tambon + โบนัสถ้าคีย์เวิร์ดอยู่ในชื่อ"""
    if not rows:
        return []
    q = _norm(query_text)
    scored = []
    for r in rows:
        name = str(r.get("name") or "")
        cat = str(r.get("category") or "")
        tmb = str(r.get("tambon") or "")
        blob = " ".join([name, cat, tmb, str(r.get("description") or ""), str(r.get("highlight") or "")]).lower()
        score = fuzz.partial_ratio(q, blob) if q else 0
        if q and q in name.lower():
            score += 25
        if prefer_category and _norm(prefer_category) in cat.lower():
            score += 15
        if prefer_tambon and _norm(prefer_tambon) in tmb.lower():
            score += 8
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]

# ----- Allowed categories by intent (ใช้กรองผลลัพธ์ให้ตรงหมวด) -----
ALLOWED_BY_INTENT = {
    "ร้านอาหาร": ["ร้านอาหาร", "อาหาร", "ข้าว", "ซีฟู้ด", "ก๋วยเตี๋ยว", "ข้าวต้ม", "ตามสั่ง", "สตรีทฟู้ด", "ของกิน"],
    "คาเฟ่": ["คาเฟ่", "กาแฟ", "เครื่องดื่ม", "ของหวาน", "ชา", "ชาเย็น", "เบเกอรี่", "คอฟฟี่"],
    "ยิม/ฟิตเนส": ["ยิม", "ฟิตเนส", "ออกกำลังกาย", "เทรนนิ่ง", "ฟิตเนต"],
    "ร้านซ่อมรถ": ["ซ่อมรถ", "อู่", "ศูนย์", "ยาง", "ปะยาง", "แบตเตอรี่", "ช่วงล่าง", "แม็ก"],
    "ปั๊มน้ำมัน": ["ปั๊ม", "ปั๊มน้ำมัน", "ptt", "บางจาก", "เชลล์", "พีที"],
    "ตลาด": ["ตลาด", "ตลาดสด", "ตลาดนัด"],
    "วัด": ["วัด", "ไหว้พระ", "ศาสนสถาน"],
    "ที่พัก": ["ที่พัก", "รีสอร์ท", "โฮมสเตย์", "โรงแรม", "เกสต์เฮาส์"],
    "สถานที่ท่องเที่ยว": ["สถานที่ท่องเที่ยว", "ชายหาด", "หาด", "อ่าว", "จุดชมวิว", "แลนด์มาร์ก", "ทะเล"],
}

def _is_allowed_for_intent(intent: Optional[str], place: Dict) -> bool:
    """คืน True ถ้าสถานที่เข้ากับเจตนา intent (เช็คทั้ง category และชื่อร้าน)"""
    if not intent:
        return True
    allow = ALLOWED_BY_INTENT.get(intent)
    if not allow:
        return True
    cat = _norm(place.get("category") or "")
    name = _norm(place.get("name") or "")
    return any(k in cat or k in name for k in allow)

# ===== เข้าใจเจตนา (LLM + ตัวอย่าง) =====
def _understand(user_input: str, history_text: str) -> dict:
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นของอำเภอปะทิว จังหวัดชุมพร "
        "ตัดสินใจว่าผู้ใช้กำลังอยาก 'ค้นหาสถานที่' หรือ 'คุยทั่วไป'. "
        "ถ้าค้นหา ให้บอก category หนึ่งใน: "
        "คาเฟ่, ร้านอาหาร, ยิม/ฟิตเนส, ร้านซ่อมรถ, ปั๊มน้ำมัน, ตลาด, วัด, ที่พัก, สถานที่ท่องเที่ยว. "
        "ถ้ามีตำบลในข้อความให้คืน tambon ด้วย (ถ้าไม่แน่ใจให้ null). "
        "ตอบเฉพาะ JSON."
    )
    examples = """
    ผู้ใช้: ยิมแถวชุมโคมีไหม
    {"want_search": true, "category": "ยิม/ฟิตเนส", "tambon": "ชุมโค", "keywords": "ยิม, ฟิตเนส"}
    ผู้ใช้: รถมีปัญหา อยากหาที่ซ่อมยาง
    {"want_search": true, "category": "ร้านซ่อมรถ", "tambon": null, "keywords": "ซ่อมรถ, ร้านยาง"}
    ผู้ใช้: หิวข้าว
    {"want_search": true, "category": "ร้านอาหาร", "tambon": null, "keywords": "อาหาร, ข้าว"}
    ผู้ใช้: อยากกินกาแฟ
    {"want_search": true, "category": "คาเฟ่", "tambon": null, "keywords": "กาแฟ, คาเฟ่"}
    ผู้ใช้: ไม่มีอะไร แค่คุยเล่น
    {"want_search": false, "category": null, "tambon": null, "keywords": null}
    """
    prompt = f"""{sys}

บริบทก่อนหน้า (ย่อ):
{history_text or "(ไม่มีประวัติ)"}

ตัวอย่าง:
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

def _reply_chitchat(user_input: str, history_text: str) -> str:
    prompt = (
        "คุณคือเพื่อนผู้ช่วยท้องถิ่นของอำเภอปะทิว "
        "ตอบสั้น สุภาพ อบอุ่น และอย่าพยายามยัดเยียดไปเรื่องสถานที่ถ้าผู้ใช้ไม่ได้ถาม\n\n"
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"ผู้ใช้: {user_input}\n"
        "ตอบ:"
    )
    try:
        res = model.generate_content(prompt)
        return (res.text or "").strip() or "ครับผม"
    except Exception:
        return "ครับผม"

# ====== โหมด "ถามต่อเกี่ยวกับสถานที่" (ข้อความล้วนจากข้อมูลที่มีอยู่) ======
FOLLOWUP_PATTERNS = [
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(เด่น|แนะนำ|signature|ซิกเนเจอร์)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(เปิดกี่โมง|ปิดกี่โมง|เวลา|ทำการ)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(ราคา|ค่าเข้า|ค่าธรรมเนียม|งบ)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(อยู่ไหน|พิกัด|แผนที่|ไปยังไง|เส้นทาง|ที่อยู่)",
    r"(เด่น|แนะนำ|signature|ซิกเนเจอร์)$",
    r"(เปิดกี่โมง|ปิดกี่โมง|เวลา|ทำการ)$",
    r"(ราคา|ค่าเข้า|ค่าธรรมเนียม|งบ)$",
    r"(อยู่ไหน|พิกัด|แผนที่|ไปยังไง|เส้นทาง|ที่อยู่)$",
]

def _looks_like_followup(q: str) -> bool:
    q = q.strip().lower()
    return any(re.search(p, q) for p in FOLLOWUP_PATTERNS)

def _extract_place_name(q: str) -> str | None:
    s = q
    for w in ["เด่นอะไร","เด่นที่อะไร","เด่น","แนะนำ","signature","ซิกเนเจอร์",
              "เปิดกี่โมง","ปิดกี่โมง","เวลา","ทำการ",
              "ราคา","ค่าเข้า","ค่าธรรมเนียม","งบ",
              "อยู่ไหน","พิกัด","แผนที่","ไปยังไง","เส้นทาง","ที่อยู่",
              "ร้านนี้","ที่นี่","ตรงนี้","สถานที่นี้"]:
        s = s.replace(w, "")
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s if len(s) >= 2 else None

def _pick_focus_place(focus_place_id, last_results, maybe_name=None):
    if focus_place_id and last_results:
        for p in last_results:
            if p.get("id") == focus_place_id:
                return p
    if last_results and len(last_results) == 1:
        return last_results[0]
    if maybe_name:
        found = search_places(keywords_any=[maybe_name], limit=5)
        if not found:
            return None
        best, score = None, -1
        for p in found:
            s = fuzz.partial_ratio(maybe_name.lower(), (p.get("name") or "").lower())
            if s > score:
                best, score = p, s
        return best
    return None

def _format_place_answer_from_existing_fields(place: dict, user_q: str) -> str:
    name = place.get("name") or "สถานที่นี้"
    highlight = (place.get("highlight") or "").strip()
    desc = (place.get("description") or "").strip()
    category = (place.get("category") or "").strip()
    tambon = (place.get("tambon") or "").strip()
    lat, lng = place.get("latitude"), place.get("longitude")

    def has(x): return bool(x and str(x).lower() not in ["none","null","nan"])

    q = user_q.lower()
    parts = []

    if any(k in q for k in ["เด่น","signature","ซิกเนเจอร์","แนะนำ"]):
        if has(highlight):
            parts.append(f"**จุดเด่นของ {name}:** {highlight}")
        elif has(desc):
            parts.append(f"{name} จุดเด่น/ภาพรวม: {desc[:220]}{'...' if len(desc)>220 else ''}")
        else:
            parts.append(f"{name} ยังไม่มีข้อมูลจุดเด่นในฐานข้อมูลครับ")

    if any(k in q for k in ["เปิดกี่โมง","ปิดกี่โมง","เวลา","ทำการ"]):
        parts.append("ตอนนี้ยังไม่ได้บันทึกเวลาเปิด-ปิดไว้ในฐานข้อมูลครับ")

    if any(k in q for k in ["ราคา","ค่าเข้า","ค่าธรรมเนียม","งบ"]):
        parts.append("ตอนนี้ยังไม่ได้บันทึกราคา/ค่าเข้าของสถานที่นี้ไว้ครับ")

    if any(k in q for k in ["อยู่ไหน","พิกัด","แผนที่","ไปยังไง","เส้นทาง","ที่อยู่"]):
        line = []
        if has(category): line.append(f"ประเภท: {category}")
        if has(tambon):   line.append(f"ตำบล: {tambon}")
        if lat and lng:   line.append(f"พิกัด: {lat:.6f},{lng:.6f}")
        parts.append(" / ".join(line) if line else "ยังไม่มีที่อยู่/พิกัดในฐานข้อมูลครับ")

    if not parts:
        summary = []
        if has(highlight): summary.append(f"จุดเด่น: {highlight}")
        elif has(desc):    summary.append(desc[:220] + ("..." if len(desc)>220 else ""))
        if has(category):  summary.append(f"ประเภท: {category}")
        if has(tambon):    summary.append(f"ตำบล: {tambon}")
        if lat and lng:    summary.append(f"พิกัด: {lat:.6f},{lng:.6f}")
        parts.append(" / ".join(summary) or f"{name} ยังไม่มีรายละเอียดมากนักครับ")

    return "\n".join(parts)

# ===== ฟังก์ชันหลัก =====
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,
    focus_place_id: Optional[int] = None,
    last_results: Optional[List[Dict]] = None,
) -> Tuple[str, List[Dict]]:
    history_text = _history_to_text(history, max_turns=8)
    last_results = last_results or []

    # —— โหมด “ถามต่อเกี่ยวกับสถานที่” → ตอบข้อความล้วน ไม่คืนการ์ด ——
    if _looks_like_followup(user_input):
        maybe_name = _extract_place_name(user_input)
        place = _pick_focus_place(focus_place_id, last_results, maybe_name)
        if place:
            return _format_place_answer_from_existing_fields(place, user_input), []
        return ("ขอชื่อสถานที่ที่คุณหมายถึงหน่อยครับ เช่น “ตลาดสดปะทิว เด่นอะไร” "
                "หรือกดปุ่ม “คุยต่อเกี่ยวกับที่นี่” จากการ์ดสถานที่ก่อนหน้าได้เลยครับ"), []

    # —— เข้าใจเจตนา (ค้นหาหรือคุยเล่น) ——
    u = _understand(user_input, history_text)

    # กัน LLM งง → เดาในเครื่องสำหรับเคสกิน/ดื่ม/หมวดยอดฮิต
    if not u.get("want_search"):
        local_cat = _local_guess_category(user_input)
        txt = user_input.lower()
        if any(w in txt for w in ["ชาเย็น", "ชา", "กาแฟ", "นม", "ของหวาน", "น้ำ", "ข้าว", "อาหาร", "หิว", "กิน"]):
            u["want_search"] = True
            u["category"] = "คาเฟ่" if any(w in txt for w in ["ชา", "กาแฟ", "คาเฟ่", "นม", "ของหวาน"]) else "ร้านอาหาร"
        elif local_cat:
            u["want_search"] = True
            u["category"] = u.get("category") or local_cat

    if not u.get("want_search"):
        return (_reply_chitchat(user_input, history_text), [])

    prefer_category = u.get("category")
    prefer_tambon = u.get("tambon")
    keywords = _extract_keywords(user_input, u.get("keywords"))

    # —— ค้นรอบแรก (ใกล้ฉันถ้ามีพิกัด) ——
    if user_lat is not None and user_lng is not None:
        base = search_places_nearby(
            user_lat, user_lng,
            category=None, tambon=prefer_tambon,
            keywords_any=keywords, limit=60, within_km=20
        )
    else:
        base = search_places(category=None, tambon=prefer_tambon,
                             keywords_any=keywords, limit=60)

    ranked = _rank(base, user_input, prefer_category, prefer_tambon, top_k=12)

    # กรองให้ตรงหมวดตามเจตนา
    filtered = [r for r in ranked if _is_allowed_for_intent(prefer_category, r)]
    if filtered:
        ranked = filtered

    # —— ผ่อนเงื่อนไขถ้าน้อย ——
    if not ranked:
        if user_lat is not None and user_lng is not None:
            base2 = search_places_nearby(
                user_lat, user_lng,
                category=None, tambon=prefer_tambon,
                keywords_any=None, limit=60, within_km=25
            )
        else:
            base2 = search_places(category=None, tambon=prefer_tambon,
                                  keywords_any=None, limit=60)
        ranked = _rank(base2, user_input, prefer_category, prefer_tambon, top_k=12)
        filtered2 = [r for r in ranked if _is_allowed_for_intent(prefer_category, r)]
        if filtered2:
            ranked = filtered2

    if not ranked:
        return ("ขอโทษนะครับ เหมือนผมอาจจะเข้าใจคลาดเคลื่อนไปนิดหน่อย ลองช่วยถามใหม่อีกทีได้ไหมครับ", [])

    intro = "ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ใกล้เคียงกับความต้องการของคุณ"
    outro = "ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", ranked)
