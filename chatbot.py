# chatbot.py — stable follow-up + choosing + strict filter + category bans
# - choose from last_results (no re-query)
# - follow-up text-only; map/where -> one place card
# - strict keyword filter to avoid off-topic
# - banned categories: respects user rejections like "ไม่เอาตลาด", "ตลาดปิดหมด"
# No DB schema changes.

import json
import re
from typing import List, Dict, Tuple, Optional, Set

import google.generativeai as genai
from rapidfuzz import fuzz

from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ---------- LLM config ----------
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(
    MODEL_NAME,
    generation_config={"max_output_tokens": 500, "temperature": 0.7, "top_p": 0.95, "top_k": 40}
)

# ---------- Dictionaries ----------
STOP_WORDS = {
    "อยาก","ช่วย","หน่อย","แถว","ที่","มี","ไหม","มั้ย","ครับ","ค่ะ","คับ","จ้า","นะ",
    "บ้าง","ขอ","หา","ด้วย","เอา","หนึ่ง","นึง","แนะนำ","ตรง","แถวไหน","ขอหน่อย"
}

# canonical categories used in DB/intent
CANON_CATS = ["คาเฟ่","ร้านอาหาร","ยิม/ฟิตเนส","ร้านซ่อมรถ","ปั๊มน้ำมัน","ตลาด","วัด","ที่พัก","สถานที่ท่องเที่ยว"]

LOCAL_CATEGORY_HINTS = {
    "ยิม/ฟิตเนส": {"ยิม","ฟิตเนส","ออกกำลัง","เวท","ฟิตเนต"},
    "ร้านซ่อมรถ": {"อู่","ซ่อมรถ","ศูนย์","ร้านยาง","ปะยาง","แบตเตอรี่","แม็ก","ช่วงล่าง"},
    "ร้านอาหาร": {"กินข้าว","ข้าว","กับข้าว","อาหาร","หิว","ก๋วยเตี๋ยว","ตามสั่ง","ซีฟู้ด","น่ากิน"},
    "คาเฟ่": {"คาเฟ่","กาแฟ","ชานม","ชาเย็น","ชา","นั่งชิล","เบเกอรี่","ของหวาน"},
    "ตลาด": {"ตลาด","ตลาดสด","ตลาดนัด"},
    "วัด": {"ไหว้พระ","วัด","ทำบุญ"},
    "ปั๊มน้ำมัน": {"ปั๊ม","เติมน้ำมัน","ปั๊มน้ำมัน","ptt","บางจาก","เชลล์","พีที"},
    "ที่พัก": {"ที่พัก","รีสอร์ท","โฮมสเตย์","โรงแรม","เกสต์เฮาส์"},
    "สถานที่ท่องเที่ยว": {"สถานที่ท่องเที่ยว","ชายหาด","หาด","อ่าว","จุดชมวิว","แลนด์มาร์ก","ทะเล"},
}

ALLOWED_BY_INTENT = {
    "ร้านอาหาร": ["ร้านอาหาร","อาหาร","ข้าว","ซีฟู้ด","ก๋วยเตี๋ยว","ข้าวต้ม","ตามสั่ง","สตรีทฟู้ด","ของกิน"],
    "คาเฟ่": ["คาเฟ่","กาแฟ","เครื่องดื่ม","ของหวาน","ชา","ชาเย็น","เบเกอรี่","คอฟฟี่"],
    "ยิม/ฟิตเนส": ["ยิม","ฟิตเนส","ออกกำลังกาย","เทรนนิ่ง","ฟิตเนต"],
    "ร้านซ่อมรถ": ["ซ่อมรถ","อู่","ศูนย์","ยาง","ปะยาง","แบตเตอรี่","ช่วงล่าง","แม็ก"],
    "ปั๊มน้ำมัน": ["ปั๊ม","ปั๊มน้ำมัน","ptt","บางจาก","เชลล์","พีที"],
    "ตลาด": ["ตลาด","ตลาดสด","ตลาดนัด"],
    "วัด": ["วัด","ไหว้พระ","ศาสนสถาน"],
    "ที่พัก": ["ที่พัก","รีสอร์ท","โฮมสเตย์","โรงแรม","เกสต์เฮาส์"],
    "สถานที่ท่องเที่ยว": ["สถานที่ท่องเที่ยว","ชายหาด","หาด","อ่าว","จุดชมวิว","แลนด์มาร์ก","ทะเล"],
}

# ---------- Utils ----------
def _safe_json(text: str) -> dict:
    if not text: return {}
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        t = "\n".join(t.split("\n")[1:])
    try:
        return json.loads(t)
    except Exception:
        return {}

def _history_to_text(history: Optional[List[Dict]], max_turns: int = 8) -> str:
    if not history: return ""
    lines = []
    for m in history[-max_turns:]:
        role = "ผู้ใช้" if m.get("role") == "user" else "AI"
        c = str(m.get("content") or "").strip()
        if c: lines.append(f"{role}: {c}")
    return "\n".join(lines)

def _norm(s: str) -> str:
    return (s or "").strip().lower()

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

def _local_guess_category(user_input: str) -> Optional[str]:
    txt = _norm(user_input)
    for cat, words in LOCAL_CATEGORY_HINTS.items():
        if any(w in txt for w in words):
            return cat
    return None

def _rank(rows: List[Dict], query_text: str, prefer_category: Optional[str],
          prefer_tambon: Optional[str], top_k: int = 12) -> List[Dict]:
    if not rows: return []
    q = _norm(query_text)
    scored = []
    for r in rows:
        name = str(r.get("name") or "")
        cat = str(r.get("category") or "")
        tmb = str(r.get("tambon") or "")
        blob = " ".join([name, cat, tmb, str(r.get("description") or ""), str(r.get("highlight") or "")]).lower()
        score = fuzz.partial_ratio(q, blob) if q else 0
        if q and q in name.lower(): score += 25
        if prefer_category and _norm(prefer_category) in cat.lower(): score += 15
        if prefer_tambon and _norm(prefer_tambon) in tmb.lower(): score += 8
        scored.append((score, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]

def _filter_by_strict_keywords(rows: List[Dict], keywords: List[str]) -> List[Dict]:
    """Keep only rows that contain any keyword in name/description/highlight/category."""
    if not keywords: return rows
    result = []
    for r in rows:
        blob = " ".join([
            str(r.get("name") or ""),
            str(r.get("description") or ""),
            str(r.get("highlight") or ""),
            str(r.get("category") or ""),
        ]).lower()
        if any(k.lower() in blob for k in keywords):
            result.append(r)
    return result

def _is_allowed_for_intent(intent: Optional[str], place: Dict) -> bool:
    if not intent: return True
    allow = ALLOWED_BY_INTENT.get(intent)
    if not allow: return True
    cat = _norm(place.get("category") or "")
    name = _norm(place.get("name") or "")
    return any(k in cat or k in name for k in allow)

def _apply_banned(rows: List[Dict], banned: Set[str]) -> List[Dict]:
    if not banned: return rows
    def banned_cat(cat: str) -> bool:
        c = (cat or "").strip()
        return any(c == b or b in c for b in banned)
    return [r for r in rows if not banned_cat(str(r.get("category") or ""))]

# ---------- Intent ----------
def _understand(user_input: str, history_text: str) -> dict:
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นของอำเภอปะทิว จังหวัดชุมพร "
        "ตัดสินใจว่าผู้ใช้กำลังอยาก 'ค้นหาสถานที่' หรือ 'คุยทั่วไป'. "
        "ถ้าค้นหา ให้บอก category หนึ่งใน: คาเฟ่, ร้านอาหาร, ยิม/ฟิตเนส, ร้านซ่อมรถ, ปั๊มน้ำมัน, ตลาด, วัด, ที่พัก, สถานที่ท่องเที่ยว. "
        "ถ้ามีตำบลในข้อความให้คืน tambon ด้วย (ถ้าไม่แน่ใจให้ null). ตอบเฉพาะ JSON."
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
        "คุณคือเพื่อนผู้ช่วยท้องถิ่นของอำเภอปะทิว ตอบสั้น สุภาพ อบอุ่น "
        "และอย่าพยายามยัดเยียดไปเรื่องสถานที่ถ้าผู้ใช้ไม่ได้ถาม\n\n"
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"ผู้ใช้: {user_input}\nตอบ:"
    )
    try:
        res = model.generate_content(prompt)
        return (res.text or "").strip() or "ครับผม"
    except Exception:
        return "ครับผม"

# ---------- Follow-up / Map / Choose detection ----------
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

def _looks_like_map_request(q: str) -> bool:
    q = (q or "").strip().lower()
    keywords = ["แผนที่","พิกัด","ไปยังไง","เส้นทาง","ที่อยู่","ไหนอะ","ตรงไหน","ขอแผนที่","เปิดแผนที่"]
    return any(k in q for k in keywords)

def _looks_like_choose_request(q: str) -> bool:
    q = q.strip().lower()
    phrases = ["เลือก","ช่วยเลือก","แนะนำ","ร้านไหนดี","ไหนดี","เลือกสักร้าน","เลือกให้หน่อย"]
    return any(p in q for p in phrases)

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

# ---------- Category ban extractor ----------
NEG_WORDS = ["ไม่เอา","ไม่อยาก","ไม่ต้อง","ไม่ใช่","ไม่เอาละ","พอแล้ว","ปิด","ปิดหมด","ไม่เปิด","เลิก"]

def _text_to_category(txt: str) -> Optional[str]:
    t = _norm(txt)
    for cat, words in LOCAL_CATEGORY_HINTS.items():
        if any(w in t for w in words):
            return cat
    for c in CANON_CATS:
        if _norm(c) in t:
            return c
    return None

def _extract_ban_categories(user_input: str, last_results: List[Dict]) -> List[str]:
    t = _norm(user_input)
    if not any(w in t for w in NEG_WORDS):
        return []
    # if explicit category in text
    cat = _text_to_category(t)
    if cat:
        return [cat]
    # if "ปิดหมด" and last results are mostly same category -> ban that
    if "ปิดหมด" in t or "ไม่เปิด" in t:
        if last_results:
            cats = [str(p.get("category") or "") for p in last_results]
            if cats:
                # pick the most common non-empty category
                from collections import Counter
                mc = Counter([c for c in cats if c]).most_common(1)
                if mc:
                    return [mc[0][0]]
    return []

# ---------- Pick focused place ----------
def _pick_focus_place(focus_place_id, last_results, maybe_name=None):
    if focus_place_id and last_results:
        for p in last_results:
            if p.get("id") == focus_place_id:
                return p
    if last_results and len(last_results) == 1:
        return last_results[0]
    if maybe_name:
        found = search_places(keywords_any=[maybe_name], limit=5)
        if not found: return None
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

def _score_for_choice(p: Dict, prefer_category: Optional[str]) -> int:
    s = 0
    if p.get("highlight"): s += min(60, len(str(p["highlight"])))
    if p.get("description"): s += min(60, len(str(p["description"])))
    if p.get("image_url"): s += 30
    if prefer_category and _is_allowed_for_intent(prefer_category, p): s += 25
    return s

# ---------- Main ----------
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,
    focus_place_id: Optional[int] = None,
    last_results: Optional[List[Dict]] = None,
    banned_categories: Optional[List[str]] = None,   # NEW
) -> Tuple[str, List[Dict], List[str]]:
    history_text = _history_to_text(history, max_turns=8)
    last_results = last_results or []
    banned_set: Set[str] = set(banned_categories or [])

    # update bans from the current message
    newly_banned = _extract_ban_categories(user_input, last_results)
    banned_set.update(newly_banned)

    # 0) choose/แนะนำจากผลล่าสุด
    if _looks_like_choose_request(user_input):
        usable = _apply_banned(last_results, banned_set)
        if not usable:
            return ("หมวดก่อนหน้านี้ไม่น่าจะเหมาะ ลองบอกหมวดใหม่ได้เลย เช่น ร้านอาหาร/คาเฟ่", [] , list(banned_set))
        prefer_cat = _local_guess_category(user_input)
        best = sorted(usable, key=lambda p: _score_for_choice(p, prefer_cat), reverse=True)[0]
        name = best.get("name", "สถานที่นี้")
        hi = best.get("highlight") or ""
        tambon = best.get("tambon") or ""
        cat = best.get("category") or ""
        reply = f"ผมขอแนะนำ **{name}** ครับ"
        if hi: reply += f" — จุดเด่น: {hi}"
        meta = []
        if tambon: meta.append(f"ตำบล {tambon}")
        if cat: meta.append(f"ประเภท {cat}")
        if meta: reply += f" ({' | '.join(meta)})"
        return reply.strip(), [], list(banned_set)

    # 1) follow-up / map
    if _looks_like_followup(user_input) or _looks_like_map_request(user_input):
        maybe_name = _extract_place_name(user_input)
        place = _pick_focus_place(focus_place_id, last_results, maybe_name)
        if place:
            if _looks_like_map_request(user_input):
                return "นี่ครับ แสดงรายละเอียดและปุ่มเปิดแผนที่ให้แล้ว", [place], list(banned_set)
            return _format_place_answer_from_existing_fields(place, user_input), [], list(banned_set)
        return ("ขอชื่อสถานที่ที่คุณหมายถึงหน่อยครับ เช่น “ตลาดเลริวเซ็น อยู่ตรงไหน” "
                "หรือกดปุ่ม “คุยต่อเกี่ยวกับที่นี่” จากการ์ดสถานที่ก่อนหน้าได้ครับ"), [], list(banned_set)

    # 2) intent
    u = _understand(user_input, history_text)

    # heuristic: ถ้าพูด "น่ากิน/อยากกิน" → ร้านอาหาร/คาเฟ่
    if not u.get("want_search"):
        local_cat = _local_guess_category(user_input)
        txt = user_input.lower()
        if any(w in txt for w in ["ชาเย็น","ชา","กาแฟ","นม","ของหวาน","น้ำ","ข้าว","อาหาร","หิว","กิน","น่ากิน"]):
            u["want_search"] = True
            u["category"] = "คาเฟ่" if any(w in txt for w in ["ชา","กาแฟ","คาเฟ่","นม","ของหวาน"]) else "ร้านอาหาร"
        elif local_cat:
            u["want_search"] = True
            u["category"] = u.get("category") or local_cat

    if not u.get("want_search"):
        return (_reply_chitchat(user_input, history_text), [], list(banned_set))

    prefer_category = u.get("category")
    prefer_tambon = u.get("tambon")
    keywords = _extract_keywords(user_input, u.get("keywords"))

    # 3) search (exclude banned categories)
    if user_lat is not None and user_lng is not None:
        base = search_places_nearby(
            user_lat, user_lng,
            category=None, tambon=prefer_tambon,
            keywords_any=keywords, limit=60, within_km=20
        )
    else:
        base = search_places(category=None, tambon=prefer_tambon, keywords_any=keywords, limit=60)

    base = _apply_banned(base, banned_set)
    ranked = _rank(base, user_input, prefer_category, prefer_tambon, top_k=12)
    filtered = [r for r in ranked if _is_allowed_for_intent(prefer_category, r)]
    if filtered: ranked = filtered

    # 4) relax if empty
    if not ranked:
        if user_lat is not None and user_lng is not None:
            base2 = search_places_nearby(
                user_lat, user_lng,
                category=None, tambon=prefer_tambon,
                keywords_any=None, limit=60, within_km=25
            )
        else:
            base2 = search_places(category=None, tambon=prefer_tambon, keywords_any=None, limit=60)
        base2 = _apply_banned(base2, banned_set)
        ranked = _rank(base2, user_input, prefer_category, prefer_tambon, top_k=12)
        filtered2 = [r for r in ranked if _is_allowed_for_intent(prefer_category, r)]
        if filtered2: ranked = filtered2

    # 5) strict keyword filter
    ranked = _filter_by_strict_keywords(ranked, keywords)
    if not ranked:
        human_kw = " ".join(keywords) if keywords else "คำค้นที่ระบุ"
        return (f"ยังไม่พบสถานที่ที่ตรงกับ {human_kw} แบบชัดเจนครับ ลองระบุคำเพิ่มได้นะ", [], list(banned_set))

    intro = "ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ที่ใกล้เคียงกับความต้องการของคุณ"
    outro = "ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", ranked, list(banned_set))
