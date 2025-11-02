import json
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
    lines=[]
    for m in history[-max_turns:]:
        role = "ผู้ใช้" if m.get("role")=="user" else "AI"
        c = str(m.get("content") or "").strip()
        if c: lines.append(f"{role}: {c}")
    return "\n".join(lines)

def _norm(s:str)->str:
    return (s or "").strip().lower()

STOP_WORDS = {"อยาก","ช่วย","หน่อย","แถว","ที่","มี","ไหม","มั้ย","ครับ","ค่ะ","คับ","จ้า","นะ","บ้าง","ขอ","หา","ด้วย","เอา","หนึ่ง","นึง","แนะนำ","ตรง","แถวไหน","ขอหน่อย"}

# เดาในเครื่อง (กันพลาด) ครอบคลุมเคสที่คุณเจอบ่อย
LOCAL_CATEGORY_HINTS = {
    "ยิม/ฟิตเนส": {"ยิม","ฟิตเนส","ออกกำลัง","เวท","ฟิตเนต"},
    "ร้านซ่อมรถ": {"อู่","ซ่อมรถ","ศูนย์","ร้านยาง","ปะยาง","แบตเตอรี่","แม็ก","ช่วงล่าง"},
    "ร้านอาหาร": {"กินข้าว","ข้าว","กับข้าว","อาหาร","หิว"},
    "คาเฟ่": {"คาเฟ่","กาแฟ","ชานม","ชาเย็น","ชา","นั่งชิล"},
    "ตลาด": {"ตลาด","ตลาดสด","ตลาดนัด"},
    "วัด": {"ไหว้พระ","วัด","ทำบุญ"},
    "ปั๊มน้ำมัน": {"ปั๊ม","เติมน้ำมัน","ปั๊มน้ำมัน","PTT","บางจาก","เชลล์","พีที"},
    "ที่พัก": {"ที่พัก","รีสอร์ท","โฮมสเตย์","โรงแรม"},
    "สถานที่ท่องเที่ยว": {"เที่ยว","ทะเล","ชายหาด","จุดชมวิว","แลนด์มาร์ก"},
}

def _local_guess_category(user_input:str)->Optional[str]:
    txt=_norm(user_input)
    for cat, words in LOCAL_CATEGORY_HINTS.items():
        if any(w in txt for w in words):
            return cat
    return None

def _extract_keywords(user_input:str, llm_keywords:Optional[str])->List[str]:
    pool=set()
    raw=_norm(user_input).replace(",", " ")
    for tok in raw.split():
        if len(tok)>=2 and tok not in STOP_WORDS:
            pool.add(tok)
    if llm_keywords:
        for tok in _norm(llm_keywords).replace(",", " ").split():
            if len(tok)>=2 and tok not in STOP_WORDS:
                pool.add(tok)
    return sorted(pool)

def _rank(rows: List[Dict], query_text: str, prefer_category: Optional[str], prefer_tambon: Optional[str], top_k:int=12) -> List[Dict]:
    """เรียงคะแนน: fuzzy + โบนัส category/tambon + โบนัสถ้าคีย์เวิร์ดอยู่ในชื่อ"""
    if not rows: return []

    q=_norm(query_text)
    scored=[]
    for r in rows:
        name=str(r.get("name") or "")
        cat=str(r.get("category") or "")
        tmb=str(r.get("tambon") or "")
        blob=" ".join([name, cat, tmb, str(r.get("description") or ""), str(r.get("highlight") or "")]).lower()

        score=fuzz.partial_ratio(q, blob) if q else 0

        # โบนัส match ตรง ๆ
        if q and q in name.lower():
            score += 25

        # โบนัสถ้า category ที่เดาไว้ไปพ้องกับ category แถวๆ นี้
        if prefer_category and _norm(prefer_category) in cat.lower():
            score += 15

        # โบนัสตำบล
        if prefer_tambon and _norm(prefer_tambon) in tmb.lower():
            score += 8

        scored.append((score, r))

    scored.sort(key=lambda x:x[0], reverse=True)
    return [r for _, r in scored[:top_k]]

# ===== เข้าใจเจตนา (LLM + เดาในเครื่อง) =====
def _understand(user_input:str, history_text:str)->dict:
    sys=(
        "คุณคือผู้ช่วยท้องถิ่นของอำเภอปะทิว จังหวัดชุมพร "
        "ตัดสินใจว่าผู้ใช้กำลังอยาก 'ค้นหาสถานที่' หรือ 'คุยทั่วไป'. "
        "ถ้าค้นหา ให้บอก category หนึ่งใน: "
        "คาเฟ่, ร้านอาหาร, ยิม/ฟิตเนส, ร้านซ่อมรถ, ปั๊มน้ำมัน, ตลาด, วัด, ที่พัก, สถานที่ท่องเที่ยว. "
        "ถ้ามีตำบลในข้อความให้คืน tambon ด้วย (ถ้าไม่แน่ใจให้ null). "
        "ตอบเฉพาะ JSON."
    )
    examples="""
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
    prompt=f"""{sys}

บริบทก่อนหน้า (ย่อ):
{history_text or "(ไม่มีประวัติ)"}

ตัวอย่าง:
{examples}

ผู้ใช้: "{user_input}"
ตอบเป็น JSON เท่านั้น:
"""
    try:
        res=model.generate_content(prompt)
        data=_safe_json(res.text)
        return {
            "want_search": bool(data.get("want_search")),
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "keywords": data.get("keywords"),
        }
    except Exception:
        return {"want_search": False, "category": None, "tambon": None, "keywords": None}

def _reply_chitchat(user_input:str, history_text:str)->str:
    prompt=(
        "คุณคือเพื่อนผู้ช่วยท้องถิ่นของอำเภอปะทิว "
        "ตอบสั้น สุภาพ อบอุ่น และอย่าพยายามยัดเยียดไปเรื่องสถานที่ถ้าผู้ใช้ไม่ได้ถาม\n\n"
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"ผู้ใช้: {user_input}\n"
        "ตอบ:"
    )
    try:
        res=model.generate_content(prompt)
        return (res.text or "").strip() or "ครับผม"
    except Exception:
        return "ครับผม"

# ===== ฟังก์ชันหลัก =====
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,
) -> Tuple[str, List[Dict]]:
    history_text=_history_to_text(history, max_turns=8)
    u=_understand(user_input, history_text)

    # ถ้า LLM งง ลองเดาในเครื่อง (กันพลาด)
    if not u.get("want_search"):
        local_cat=_local_guess_category(user_input)
        if local_cat:
            u["want_search"]=True
            u["category"]=u.get("category") or local_cat

    if not u.get("want_search"):
        return (_reply_chitchat(user_input, history_text), [])

    prefer_category=u.get("category")
    prefer_tambon=u.get("tambon")

    # รวมคีย์เวิร์ด: จาก LLM + แตกเอง
    keywords=_extract_keywords(user_input, u.get("keywords"))

    # 1) ลองค้นแบบมีพิกัด (ถ้ามี) หรือไม่มีก็ค้นทั่วไป
    if user_lat is not None and user_lng is not None:
        base=search_places_nearby(user_lat, user_lng, category=None, tambon=prefer_tambon,
                                  keywords_any=keywords, limit=60, within_km=20)
    else:
        base=search_places(category=None, tambon=prefer_tambon,
                           keywords_any=keywords, limit=60)

    # 2) จัดอันดับ โดยให้โบนัสกับ category/tambon ที่เดาไว้
    ranked=_rank(base, user_input, prefer_category, prefer_tambon, top_k=12)

    # 3) ถ้าน้อย → ผ่อนเงื่อนไข (ตัดคีย์เวิร์ด ใช้แต่ tambon/ทั้งอำเภอ)
    if not ranked:
        if user_lat is not None and user_lng is not None:
            base2=search_places_nearby(user_lat, user_lng, category=None,
                                       tambon=prefer_tambon, keywords_any=None, limit=60, within_km=25)
        else:
            base2=search_places(category=None, tambon=prefer_tambon, keywords_any=None, limit=60)
        ranked=_rank(base2, user_input, prefer_category, prefer_tambon, top_k=12)

    if not ranked:
        return ("ขอโทษนะครับ เหมือนผมอาจจะเข้าใจคลาดเคลื่อนนิดหน่อย ลองช่วยถามใหม่อีกทีได้ไหมครับ", [])

    intro="ตอนนี้มีสถานที่ไหนที่คุณต้องการบ้างมั้ยครับ บอกผมมาได้เลยนะ เผื่อผมมีสถานที่ใกล้เคียงกับความต้องการของคุณ"
    outro="ถ้ายังไม่ตรงใจ บอกเพิ่มได้นะครับ เดี๋ยวผมช่วยหาต่อให้เองครับ"
    return (f"{intro}\n\n{outro}", ranked)
