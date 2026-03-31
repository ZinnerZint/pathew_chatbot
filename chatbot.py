import json
import re
from typing import List, Dict, Tuple, Optional, Set

import google.generativeai as genai
from rapidfuzz import fuzz

from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ---------- LLM config ----------
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is empty. Check your secrets!")

genai.configure(api_key=GEMINI_API_KEY)

MODEL_NAME = "gemini-2.5-flash"
model = genai.GenerativeModel(
    MODEL_NAME,
    generation_config={
        "max_output_tokens": 500,
        "temperature": 0.7,
        "top_p": 0.95,
        "top_k": 40,
    }
)

# ---------- Dictionaries ----------
STOP_WORDS = {
    "อยาก", "ช่วย", "หน่อย", "แถว", "ที่", "มี", "ไหม", "มั้ย", "ครับ", "ค่ะ", "คับ", "จ้า", "นะ",
    "บ้าง", "ขอ", "หา", "ด้วย", "เอา", "หนึ่ง", "นึง", "แนะนำ", "ตรง", "แถวไหน", "ขอหน่อย",
    "หน่อยสิ", "หน่อยนะ", "หน่อยดิ", "ให้หน่อย", "ใกล้", "ใกล้ๆ", "ใกล้ๆกัน", "ใกล้กัน",
    "แถวนี้", "แถวนั้น", "ละแวกนี้", "รอบๆ", "แถว", "ใกล้กับ", "ใกล้เคียง"
}

CANON_CATS = [
    "คาเฟ่", "ร้านอาหาร", "ที่พัก", "สถานที่ท่องเที่ยว", "ปั๊มน้ำมัน",
    "วัด", "ตลาด", "ร้านซ่อมรถ", "ร้านตัดผม", "ร้านขายยา",
    "ร้านสะดวกซื้อ", "ธนาคาร", "มัสยิด", "สถานที่ราชการ",
    "โรงยิม", "สถานีรถไฟ", "ล้างอัดฉีด", "ร้านของฝาก",
    "ศูนย์จำหน่ายรถ", "อุตสาหกรรม"
]

CATEGORY_SYNONYMS = {
    "คาเฟ่": ["คาเฟ่", "ร้านกาแฟ", "ร้านชา", "เครื่องดื่ม", "น้ำปั่น", "ชานม", "ชาเย็น", "นั่งชิล", "นั่งชิลล์"],
    "ร้านอาหาร": ["ร้านอาหาร", "ร้านข้าว", "ของกิน", "อาหาร", "ของอร่อย", "อาหารทะเล", "ซีฟู้ด"],
    "ที่พัก": ["ที่พัก", "โรงแรม", "รีสอร์ท", "โฮมสเตย์", "เกสต์เฮาส์"],
    "สถานที่ท่องเที่ยว": ["สถานที่ท่องเที่ยว", "ชายหาด", "ทะเล", "ภูเขา", "อ่าว", "หาด", "จุดชมวิว", "แลนด์มาร์ก"],
    "ปั๊มน้ำมัน": ["ปั๊มน้ำมัน", "ปั๊ม"],
    "วัด": ["วัด", "สำนักสงฆ์"],
    "ตลาด": ["ตลาด", "ตลาดสด", "ตลาดนัด"],
    "ร้านซ่อมรถ": ["ร้านซ่อมรถ", "อู่", "ร้านยาง", "ปะยาง"],
    "ร้านตัดผม": ["ร้านตัดผม", "ร้านเสริมสวย", "บาร์เบอร์", "ซาลอน"],
    "ร้านขายยา": ["ร้านขายยา", "โรงพยาบาล", "อนามัย", "คลินิก"],
    "ร้านสะดวกซื้อ": ["ร้านสะดวกซื้อ", "ห้างสรรพสินค้า", "ร้านขายของใช้ในบ้าน", "มินิมาร์ท"],
    "ธนาคาร": ["ธนาคาร", "atm", "เอทีเอ็ม"],
    "มัสยิด": ["มัสยิด"],
    "สถานที่ราชการ": ["สถานที่ราชการ", "อบต", "เทศบาล", "อำเภอ", "หน่วยงานรัฐ"],
    "โรงยิม": ["โรงยิม", "ยิม", "ฟิตเนส"],
    "สถานีรถไฟ": ["สถานีรถไฟ", "รถไฟ"],
    "ล้างอัดฉีด": ["ล้าง อัด ฉีด", "ล้างอัดฉีด", "ล้างรถ"],
    "ร้านของฝาก": ["ของฝาก", "ร้านค้า"],
    "ศูนย์จำหน่ายรถ": ["ศูนย์จำหน่ายรถ", "โชว์รูมรถ"],
    "อุตสาหกรรม": ["อุตสาหกรรม", "โรงงาน"],
}

LOCAL_CATEGORY_HINTS = {
    "คาเฟ่": {
        "คาเฟ่", "ร้านกาแฟ", "กาแฟ", "ชาเย็น", "ชา", "ชานม", "เบเกอรี่", "ของหวาน",
        "ร้านชา", "นั่งชิล", "นั่งชิลล์", "ชิล", "น้ำ", "เครื่องดื่ม", "น้ำปั่น", "โกโก้", "ชาไทย"
    },
    "ร้านอาหาร": {
        "กินข้าว", "ข้าว", "กับข้าว", "อาหาร", "หิว", "ก๋วยเตี๋ยว", "ตามสั่ง", "ซีฟู้ด",
        "น่ากิน", "ของกิน", "กินอะไรดี", "มีอะไรให้กิน", "ร้านข้าว", "หมูกระทะ", "ส้มตำ",
        "ชาบู", "ปิ้งย่าง", "ข้าวแกง", "อาหารทะเล", "ร้านแนะนำ", "อิ่ม", "ของอร่อย"
    },
    "ที่พัก": {"ที่พัก", "โรงแรม", "รีสอร์ท", "โฮมสเตย์", "เกสต์เฮาส์", "พักค้าง", "นอนพัก"},
    "สถานที่ท่องเที่ยว": {"สถานที่ท่องเที่ยว", "ชายหาด", "หาด", "อ่าว", "จุดชมวิว", "แลนด์มาร์ก", "ทะเล", "เที่ยว", "ภูเขา"},
    "ปั๊มน้ำมัน": {"ปั๊ม", "เติมน้ำมัน", "ปั๊มน้ำมัน", "ptt", "บางจาก", "เชลล์", "พีที"},
    "วัด": {"ไหว้พระ", "วัด", "ทำบุญ", "สำนักสงฆ์"},
    "ตลาด": {"ตลาด", "ตลาดสด", "ตลาดนัด", "ซื้อของ"},
    "ร้านซ่อมรถ": {"อู่", "ซ่อมรถ", "ร้านยาง", "ปะยาง", "แบตเตอรี่", "แม็ก", "ช่วงล่าง"},
    "ร้านตัดผม": {"ร้านตัดผม", "ตัดผม", "เสริมสวย", "บาร์เบอร์", "ซาลอน"},
    "ร้านขายยา": {"ร้านขายยา", "เภสัช", "โรงพยาบาล", "อนามัย", "คลินิก", "ร้านยา"},
    "ร้านสะดวกซื้อ": {"ร้านสะดวกซื้อ", "มินิมาร์ท", "ห้าง", "ห้างสรรพสินค้า", "ของใช้ในบ้าน"},
    "ธนาคาร": {"ธนาคาร", "atm", "เอทีเอ็ม"},
    "มัสยิด": {"มัสยิด"},
    "สถานที่ราชการ": {"สถานที่ราชการ", "อำเภอ", "อบต", "เทศบาล", "หน่วยงานรัฐ"},
    "โรงยิม": {"โรงยิม", "ยิม", "ฟิตเนส", "ออกกำลังกาย", "เวท"},
    "สถานีรถไฟ": {"สถานีรถไฟ", "รถไฟ"},
    "ล้างอัดฉีด": {"ล้างรถ", "ล้าง อัด ฉีด", "ล้างอัดฉีด"},
    "ร้านของฝาก": {"ของฝาก", "ร้านค้า"},
    "ศูนย์จำหน่ายรถ": {"ศูนย์จำหน่ายรถ", "โชว์รูมรถ"},
    "อุตสาหกรรม": {"โรงงาน", "อุตสาหกรรม"},
}

ALLOWED_BY_INTENT = {
    "คาเฟ่": CATEGORY_SYNONYMS["คาเฟ่"],
    "ร้านอาหาร": CATEGORY_SYNONYMS["ร้านอาหาร"],
    "ที่พัก": CATEGORY_SYNONYMS["ที่พัก"],
    "สถานที่ท่องเที่ยว": CATEGORY_SYNONYMS["สถานที่ท่องเที่ยว"],
    "ปั๊มน้ำมัน": CATEGORY_SYNONYMS["ปั๊มน้ำมัน"],
    "วัด": CATEGORY_SYNONYMS["วัด"],
    "ตลาด": CATEGORY_SYNONYMS["ตลาด"],
    "ร้านซ่อมรถ": CATEGORY_SYNONYMS["ร้านซ่อมรถ"] + CATEGORY_SYNONYMS["ศูนย์จำหน่ายรถ"],
    "ร้านตัดผม": CATEGORY_SYNONYMS["ร้านตัดผม"],
    "ร้านขายยา": CATEGORY_SYNONYMS["ร้านขายยา"],
    "ร้านสะดวกซื้อ": CATEGORY_SYNONYMS["ร้านสะดวกซื้อ"],
    "ธนาคาร": CATEGORY_SYNONYMS["ธนาคาร"],
    "มัสยิด": CATEGORY_SYNONYMS["มัสยิด"],
    "สถานที่ราชการ": CATEGORY_SYNONYMS["สถานที่ราชการ"],
    "โรงยิม": CATEGORY_SYNONYMS["โรงยิม"],
    "สถานีรถไฟ": CATEGORY_SYNONYMS["สถานีรถไฟ"],
    "ล้างอัดฉีด": CATEGORY_SYNONYMS["ล้างอัดฉีด"],
    "ร้านของฝาก": CATEGORY_SYNONYMS["ร้านของฝาก"],
    "ศูนย์จำหน่ายรถ": CATEGORY_SYNONYMS["ศูนย์จำหน่ายรถ"],
    "อุตสาหกรรม": CATEGORY_SYNONYMS["อุตสาหกรรม"],
}

NEG_WORDS = ["ไม่เอา", "ไม่อยาก", "ไม่ต้อง", "ไม่ใช่", "ไม่เอาละ", "พอแล้ว", "ปิด", "ปิดหมด", "ไม่เปิด", "เลิก"]

FOOD_INTENT_WORDS = [
    "หิว", "กิน", "ของกิน", "อาหาร", "ข้าว", "ก๋วยเตี๋ยว", "ตามสั่ง",
    "ซีฟู้ด", "อาหารทะเล", "มีอะไรให้กิน", "กินอะไรดี", "ร้านแนะนำ", "ร้านอาหาร",
    "ร้านข้าว", "ของอร่อย", "อิ่ม"
]
CAFE_INTENT_WORDS = [
    "กาแฟ", "ชา", "คาเฟ่", "ของหวาน", "เบเกอรี่", "ชานม", "ร้านกาแฟ", "ร้านชา",
    "น้ำ", "เครื่องดื่ม", "น้ำปั่น", "โกโก้", "ชาไทย", "ชาเย็น", "นั่งชิลล์", "ถ่ายรูป", "รับลม"
]
TRAVEL_INTENT_WORDS = ["เที่ยว", "ที่เที่ยว", "หาด", "ทะเล", "อ่าว", "สถานที่ท่องเที่ยว", "ชายหาด", "ภูเขา"]
HOTEL_INTENT_WORDS = ["ที่พัก", "โรงแรม", "รีสอร์ท", "โฮมสเตย์", "เกสต์เฮาส์", "พักค้าง", "นอนพัก"]
GAS_INTENT_WORDS = ["ปั๊ม", "เติมน้ำมัน", "น้ำมันหมด", "ปั๊มน้ำมัน"]
GYM_INTENT_WORDS = ["ยิม", "ฟิตเนส", "ออกกำลังกาย", "โรงยิม", "เวท"]
CAR_INTENT_WORDS = ["ซ่อมรถ", "อู่", "ปะยาง", "แบตเตอรี่", "ร้านยาง", "ศูนย์รถ", "ศูนย์จำหน่ายรถ", "รถเสีย", "รถพัง", "สตาร์ทไม่ติด"]
MARKET_INTENT_WORDS = ["ตลาด", "ซื้อของ", "ตลาดสด", "ตลาดนัด"]
TEMPLE_INTENT_WORDS = ["วัด", "ไหว้พระ", "ทำบุญ", "สำนักสงฆ์"]
PHARMACY_INTENT_WORDS = ["ร้านขายยา", "โรงพยาบาล", "อนามัย", "คลินิก", "ป่วย", "เภสัช"]
CONVENIENCE_INTENT_WORDS = ["ร้านสะดวกซื้อ", "มินิมาร์ท", "ห้าง", "ห้างสรรพสินค้า", "ของใช้ในบ้าน", "ร้านค้า", "ของกิน"]
BANK_INTENT_WORDS = ["ธนาคาร", "atm", "เอทีเอ็ม", "ฝากเงิน", "ถอนเงิน", "กู้เงิน"]
MOSQUE_INTENT_WORDS = ["มัสยิด"]
GOV_INTENT_WORDS = ["สถานที่ราชการ", "อบต", "เทศบาล", "อำเภอ", "ราชการ"]
TRAIN_INTENT_WORDS = ["สถานีรถไฟ", "รถไฟ"]
WASH_INTENT_WORDS = ["ล้างรถ", "ล้างอัดฉีด", "ล้าง อัด ฉีด"]
SOUVENIR_INTENT_WORDS = ["ของฝาก"]
INDUSTRY_INTENT_WORDS = ["โรงงาน", "อุตสาหกรรม"]

NEARBY_WORDS = [
    "ใกล้", "ใกล้ๆ", "ใกล้กัน", "ใกล้ๆกัน", "ใกล้กับ", "แถวนี้", "แถวนั้น",
    "ละแวกนี้", "รอบๆ", "ใกล้เคียง", "แถว", "ติดกับ", "ใกล้หาด", "ใกล้ที่นี่"
]

REFERENCE_STRIP_WORDS = [
    "ใกล้", "ใกล้ๆ", "ใกล้กัน", "ใกล้ๆกัน", "ใกล้กับ", "แถวนี้", "แถวนั้น",
    "ละแวกนี้", "รอบๆ", "ใกล้เคียง", "แถว", "ติดกับ", "ที่นี่", "ตรงนี้", "สถานที่นี้",
    "มี", "ไหม", "มั้ย", "บ้าง", "หน่อย", "ช่วย", "หา", "ขอ"
]

FOLLOWUP_PATTERNS = [
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(เด่น|แนะนำ|signature|ซิกเนเจอร์)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(เปิดกี่โมง|ปิดกี่โมง|เวลา|ทำการ)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(ราคา|ค่าเข้า|ค่าธรรมเนียม|งบ)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(อยู่ไหน|พิกัด|แผนที่|ไปยังไง|เส้นทาง|ที่อยู่)",
    r"(ร้านนี้|ที่นี่|ตรงนี้|สถานที่นี้).*(รูป|ภาพ|มีรูปไหม|ขอรูป|ดูรูป)",
    r"(เด่น|แนะนำ|signature|ซิกเนเจอร์)$",
    r"(เปิดกี่โมง|ปิดกี่โมง|เวลา|ทำการ)$",
    r"(ราคา|ค่าเข้า|ค่าธรรมเนียม|งบ)$",
    r"(อยู่ไหน|พิกัด|แผนที่|ไปยังไง|เส้นทาง|ที่อยู่)$",
    r"(รูป|ภาพ|มีรูปไหม|ขอรูป|ดูรูป)$",
]



PHOTO_SPOT_WORDS = [
    "ถ่ายรูป", "ถ่ายภาพ", "มุมถ่ายรูป", "จุดถ่ายรูป", "วิวสวย", "ถ่ายคอนเทนต์",
    "ถ่ายเล่น", "ถ่ายรูปสวย", "ถ่ายรูปชิลๆ", "ถ่ายสตอรี่", "ถ่ายรูปลงไอจี", "ถ่ายไอจี"
]

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

def _normalize_place_name(s: str) -> str:
    s = _norm(s)
    s = re.sub(r"\s+", "", s)
    return s
def _normalize_loose_text(s: str) -> str:
    s = _norm(s)
    s = re.sub(r"[\s\-_]+", "", s)
    return s

def _is_similar_name(q: str, candidate: str, threshold: int = 88) -> bool:
    qn = _normalize_loose_text(q)
    cn = _normalize_loose_text(candidate)
    if not qn or not cn:
        return False
    if qn == cn:
        return True
    return fuzz.ratio(qn, cn) >= threshold

def _split_category_tags(cat_value: str) -> List[str]:
    if not cat_value:
        return []
    parts = [p.strip().lower() for p in str(cat_value).split(",")]
    return [p for p in parts if p]

def _category_matches_intent(place_category: str, intent: Optional[str]) -> bool:
    if not intent:
        return True

    synonyms = [_norm(x) for x in ALLOWED_BY_INTENT.get(intent, [intent])]
    place_tags = _split_category_tags(place_category)

    full_cat = _norm(place_category)
    if any(s in full_cat for s in synonyms):
        return True

    for tag in place_tags:
        if any(s == tag or s in tag for s in synonyms):
            return True

    return False

def _extract_keywords(user_input: str, llm_keywords: Optional[str]) -> List[str]:
    pool = set()

    def add_tokens(text: str):
        text = _norm(text).replace(",", " ")
        if not text:
            return

        for tok in text.split():
            tok = tok.strip()
            if len(tok) >= 2 and tok not in STOP_WORDS:
                pool.add(tok)
                pool.add(_normalize_loose_text(tok))

        compact = _normalize_loose_text(text)
        if len(compact) >= 2 and compact not in STOP_WORDS:
            pool.add(compact)

    add_tokens(user_input)
    if llm_keywords:
        add_tokens(llm_keywords)

    return sorted([x for x in pool if x])

def _extract_keywords_for_nearby(user_input: str, llm_keywords: Optional[str], prefer_category: Optional[str]) -> List[str]:
    raw_keywords = _extract_keywords(user_input, llm_keywords)
    prefer_cat_norm = _norm(prefer_category or "")
    cat_syns = [_norm(x) for x in CATEGORY_SYNONYMS.get(prefer_category or "", [prefer_category or ""])]
    strip_words = {_norm(w) for w in REFERENCE_STRIP_WORDS}

    cleaned = []
    for k in raw_keywords:
        kk = _norm(k)
        if kk in strip_words:
            continue
        if prefer_cat_norm and prefer_cat_norm in kk:
            continue
        if any(s and s in kk for s in cat_syns):
            continue
        cleaned.append(k)

    return cleaned

def _local_guess_category(user_input: str) -> Optional[str]:
    txt = _norm(user_input)
    scores = {}

    for cat, words in LOCAL_CATEGORY_HINTS.items():
        score = sum(1 for w in words if w in txt)
        if score > 0:
            scores[cat] = score

    if not scores:
        return None

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[0][0]

def _intent_from_keywords(user_input: str) -> Optional[str]:
    txt = _norm(user_input)

    priority_checks = [
        ("ที่พัก", HOTEL_INTENT_WORDS),
        ("ร้านขายยา", PHARMACY_INTENT_WORDS),
        ("ร้านอาหาร", FOOD_INTENT_WORDS),
        ("คาเฟ่", CAFE_INTENT_WORDS),
        ("ปั๊มน้ำมัน", GAS_INTENT_WORDS),
        ("โรงยิม", GYM_INTENT_WORDS),
        ("ร้านซ่อมรถ", CAR_INTENT_WORDS),
        ("ตลาด", MARKET_INTENT_WORDS),
        ("วัด", TEMPLE_INTENT_WORDS),
        ("ร้านสะดวกซื้อ", CONVENIENCE_INTENT_WORDS),
        ("ธนาคาร", BANK_INTENT_WORDS),
        ("มัสยิด", MOSQUE_INTENT_WORDS),
        ("สถานที่ราชการ", GOV_INTENT_WORDS),
        ("สถานีรถไฟ", TRAIN_INTENT_WORDS),
        ("ล้างอัดฉีด", WASH_INTENT_WORDS),
        ("ร้านของฝาก", SOUVENIR_INTENT_WORDS),
        ("อุตสาหกรรม", INDUSTRY_INTENT_WORDS),
        ("สถานที่ท่องเที่ยว", TRAVEL_INTENT_WORDS),
    ]

    best_cat = None
    best_score = 0

    for cat, words in priority_checks:
        score = sum(1 for w in words if w in txt)
        if score > best_score:
            best_score = score
            best_cat = cat

    return best_cat

def _forced_category_fallback(user_input: str) -> Optional[str]:
    txt = _norm(user_input)

    # ต้องเช็กอาหารก่อนคำว่า "ทะเล"
    if any(w in txt for w in ["อาหารทะเล", "ซีฟู้ด", "ของกิน", "หิว", "กิน", "อาหาร", "ข้าว", "ก๋วยเตี๋ยว", "ร้านข้าว"]):
        return "ร้านอาหาร"

    if any(w in txt for w in ["ทำบุญ", "ไหว้พระ", "วัด", "สำนักสงฆ์"]):
        return "วัด"

    if any(w in txt for w in ["ถ่ายรูป", "ถ่ายภาพ", "มุมถ่ายรูป", "จุดถ่ายรูป", "วิวสวย", "ถ่ายคอนเทนต์", "ถ่ายสตอรี่", "ถ่ายไอจี"]):
        return "สถานที่ท่องเที่ยว"

    if any(w in txt for w in ["น้ำ", "ดื่ม", "กาแฟ", "ชา", "คาเฟ่", "เครื่องดื่ม", "น้ำปั่น", "ชานม", "โกโก้", "นั่งชิล", "นั่งชิลล์", "ชิล"]):
        return "คาเฟ่"

    if any(w in txt for w in ["พัก", "โรงแรม", "รีสอร์ท", "ที่พัก", "โฮมสเตย์"]):
        return "ที่พัก"

    if any(w in txt for w in ["คลินิก", "โรงพยาบาล", "อนามัย", "ร้านขายยา", "ร้านยา", "เภสัช"]):
        return "ร้านขายยา"

    if any(w in txt for w in ["ตัดผม", "บาร์เบอร์", "เสริมสวย", "ซาลอน"]):
        return "ร้านตัดผม"

    if any(w in txt for w in ["อู่", "ซ่อมรถ", "ปะยาง", "แบตเตอรี่", "ร้านยาง"]):
        return "ร้านซ่อมรถ"

    if any(w in txt for w in ["ปั๊ม", "เติมน้ำมัน", "น้ำมันหมด"]):
        return "ปั๊มน้ำมัน"

    if any(w in txt for w in ["ทะเล", "ชายหาด", "หาด", "อ่าว", "จุดชมวิว", "ที่เที่ยว", "เที่ยว"]):
        return "สถานที่ท่องเที่ยว"

    return None

def _is_strict_category(prefer_category: Optional[str]) -> bool:
    return prefer_category in {
        "วัด",
        "สถานที่ท่องเที่ยว",
        "มัสยิด",
        "ธนาคาร",
        "สถานที่ราชการ",
        "สถานีรถไฟ",
    }

def _infer_category_from_places(places: List[Dict]) -> Optional[str]:
    if not places:
        return None

    score_map = {}

    for p in places:
        cat = str(p.get("category") or "")
        for canon in CANON_CATS:
            if _category_matches_intent(cat, canon):
                score_map[canon] = score_map.get(canon, 0) + 1

    if not score_map:
        return None

    return sorted(score_map.items(), key=lambda x: x[1], reverse=True)[0][0]

def _post_filter_results_by_query(rows: List[Dict], user_input: str, prefer_category: Optional[str]) -> List[Dict]:
    if not rows:
        return rows

    txt = _norm(user_input)

    if prefer_category == "วัด" or any(w in txt for w in ["ทำบุญ", "ไหว้พระ", "วัด", "สำนักสงฆ์"]):
        return [r for r in rows if _is_allowed_for_intent("วัด", r)]

    if prefer_category == "สถานที่ท่องเที่ยว" and any(w in txt for w in ["ทะเล", "ชายหาด", "หาด", "อ่าว", "จุดชมวิว", "ที่เที่ยว", "เที่ยว"]):
        return [r for r in rows if _is_allowed_for_intent("สถานที่ท่องเที่ยว", r)]

    return rows

def _strict_category_filter(rows: List[Dict], prefer_category: Optional[str]) -> List[Dict]:
    if not rows or not prefer_category:
        return rows

    strict_cats = {
        "ร้านอาหาร",
        "คาเฟ่",
        "ที่พัก",
        "วัด",
        "ร้านขายยา",
        "ร้านตัดผม",
        "ร้านซ่อมรถ",
    }

    if prefer_category not in strict_cats:
        return rows

    return [r for r in rows if _is_allowed_for_intent(prefer_category, r)]

def _looks_like_explicit_place_name_query(user_input: str) -> bool:
    txt = _norm(user_input)

    broad_words = [
        "มี", "ไหม", "มั้ย", "แนะนำ", "ใกล้", "ใกล้ๆ", "ที่ไหน",
        "อะไร", "บ้าง", "ช่วย", "หน่อย", "เอา", "ขอ", "หา", "อยาก", "ไป",
        "ร้าน", "คาเฟ่", "ที่พัก", "ปั๊ม", "ตลาด", "โรงแรม", "รีสอร์ท", "โรงพยาบาล", "คลินิก"
    ]

    if any(w in txt for w in broad_words):
        return False

    if len(txt.strip()) < 3:
        return False

    return True

def _find_exact_name_matches(user_input: str, rows: List[Dict]) -> List[Dict]:
    qn = _normalize_loose_text(user_input)
    if not qn:
        return []

    exact = []
    near_exact = []

    for r in rows:
        name = str(r.get("name") or "")
        nn = _normalize_loose_text(name)

        if nn == qn:
            exact.append(r)
        elif fuzz.ratio(qn, nn) >= 88:
            near_exact.append(r)

    return exact if exact else near_exact

def _rank(rows: List[Dict], query_text: str, prefer_category: Optional[str], prefer_tambon: Optional[str], top_k: int = 12) -> List[Dict]:
    if not rows:
        return []

    q = _norm(query_text)
    q_norm = _normalize_loose_text(query_text)
    scored = []

    for r in rows:
        name = str(r.get("name") or "")
        cat = str(r.get("category") or "")
        tmb = str(r.get("tambon") or "")
        desc = str(r.get("description") or "")
        hi = str(r.get("highlight") or "")

        name_norm = _normalize_loose_text(name)
        blob = " ".join([name, cat, tmb, desc, hi]).lower()
        blob_norm = _normalize_loose_text(blob)

        score = 0

        if q:
            score += fuzz.partial_ratio(q, blob)

        if q_norm and blob_norm:
            score += int(fuzz.partial_ratio(q_norm, blob_norm) * 0.35)

        if q_norm and name_norm:
            if q_norm == name_norm:
                score += 1500
            else:
                name_ratio = fuzz.ratio(q_norm, name_norm)
                if name_ratio >= 92:
                    score += 700
                elif name_ratio >= 88:
                    score += 400
                elif q_norm in name_norm or name_norm in q_norm:
                    score += 180

        if q and q in name.lower():
            score += 40

        if prefer_category:
            if _category_matches_intent(cat, prefer_category):
                score += 80
            else:
                score -= 500

        if prefer_tambon and _norm(prefer_tambon) in tmb.lower():
            score += 30

        if hi:
            score += 5
        if desc:
            score += 4
        if r.get("image_url"):
            score += 4

        scored.append((score, r))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:top_k]]

def _is_allowed_for_intent(intent: Optional[str], place: Dict) -> bool:
    if not intent:
        return True
    cat = str(place.get("category") or "")
    return _category_matches_intent(cat, intent)

def _apply_banned(rows: List[Dict], banned: Set[str]) -> List[Dict]:
    if not banned:
        return rows

    def banned_cat(cat: str) -> bool:
        c = (cat or "").strip().lower()
        cat_tags = _split_category_tags(c)
        for b in banned:
            bb = _norm(b)
            if bb in c:
                return True
            if any(bb == tag or bb in tag for tag in cat_tags):
                return True
        return False

    return [r for r in rows if not banned_cat(str(r.get("category") or ""))]

def _is_broad_query(user_input: str, keywords: List[str]) -> bool:
    txt = _norm(user_input)

    broad_markers = [
        "หิว", "มีอะไรให้กิน", "กินอะไรดี", "มีร้านแนะนำไหม", "ร้านแนะนำ",
        "มีโรงพยาบาลไหม", "มีโรงพยาบาลแถวนี้ไหม", "มีร้านขายยาไหม", "มีคลินิกไหม",
        "มีที่พักไหม", "มีคาเฟ่ไหม", "มีร้านอาหารไหม",
        "มีวัดไหม", "มีตลาดไหม", "มีปั๊มไหม", "มีธนาคารไหม",
        "มีมัสยิดไหม", "มีสถานีรถไฟไหม", "อยากกินน้ำ", "อยากกินกาแฟ"
    ]

    if any(w in txt for w in broad_markers):
        return True

    if len(keywords) == 1 and len(keywords[0]) >= 10:
        return True

    return len(keywords) == 0

def _category_examples_text() -> str:
    return (
        "ลองบอกประเภทเพิ่มได้ครับ เช่น\n"
        "- คาเฟ่ / ร้านกาแฟ\n"
        "- ร้านอาหาร\n"
        "- ที่เที่ยว\n"
        "- ที่พัก\n"
        "- ร้านขายยา"
    )

def _fallback_reply(user_input: str, prefer_category: Optional[str]) -> str:
    forced = prefer_category or _forced_category_fallback(user_input)

    if forced == "วัด":
        return "ตอนนี้ผมยังไม่พบข้อมูลสถานที่ทำบุญหรือวัดที่ตรงคำนี้ครับ ลองพิมพ์ชื่อตำบลหรือชื่อวัดที่ต้องการเพิ่มได้ครับ "

    if forced == "สถานที่ท่องเที่ยว":
        return "ตอนนี้ผมยังไม่พบข้อมูลที่เป็นสถานที่ท่องเที่ยวประเภททะเลหรือชายหาดแบบตรงคำนี้ครับ ลองพิมพ์ชื่อหาด อ่าว หรือชื่อตำบลเพิ่มได้ครับ "

    if forced == "คาเฟ่":
        return "ผมยังหาไม่เจอแบบตรงคำนี้ครับ แต่ถ้าต้องการ ผมช่วยหาร้านคาเฟ่หรือร้านเครื่องดื่มใกล้เคียงให้ได้นะครับ "

    if forced == "ร้านอาหาร":
        return "ผมยังหาไม่เจอแบบตรงคำนี้ครับ แต่ผมช่วยหาร้านอาหารใกล้เคียงให้แทนได้นะครับ 🍽"

    if forced == "ที่พัก":
        return "ผมยังหาไม่เจอแบบตรงคำนี้ครับ แต่ผมช่วยหาที่พักใกล้เคียงให้แทนได้นะครับ "

    if forced == "ร้านขายยา":
        return "ผมยังหาไม่เจอแบบตรงคำนี้ครับ แต่ผมช่วยหาร้านขายยา คลินิก หรือโรงพยาบาลใกล้เคียงให้แทนได้นะครับ "

    return "ผมอาจยังตีความคำนี้ไม่ครบครับ \n" + _category_examples_text()

def _search_by_context(
    user_input: str,
    user_lat: Optional[float],
    user_lng: Optional[float],
    prefer_tambon: Optional[str],
    keywords: Optional[List[str]],
    prefer_category: Optional[str] = None,
    limit: int = 30
) -> List[Dict]:
    if user_lat is not None and user_lng is not None:
        return search_places_nearby(
            user_lat,
            user_lng,
            category=prefer_category,
            tambon=prefer_tambon,
            keywords_any=keywords,
            limit=limit
        )
    return search_places(
        category=prefer_category,
        tambon=prefer_tambon,
        keywords_any=keywords,
        limit=limit
    )

def _broader_category_fallback(
    user_input: str,
    user_lat: Optional[float],
    user_lng: Optional[float],
    prefer_tambon: Optional[str],
    prefer_category: Optional[str],
    banned_set: Set[str]
) -> List[Dict]:
    base = _search_by_context(
        user_input=user_input,
        user_lat=user_lat,
        user_lng=user_lng,
        prefer_tambon=prefer_tambon,
        keywords=None,
        prefer_category=prefer_category,
        limit=40
    )
    base = _apply_banned(base, banned_set)

    if prefer_category:
        filtered = [p for p in base if _is_allowed_for_intent(prefer_category, p)]
        filtered = _strict_category_filter(filtered, prefer_category)
        filtered = _post_filter_results_by_query(filtered, user_input, prefer_category)

        if _is_strict_category(prefer_category):
            return _rank(filtered, user_input, prefer_category, prefer_tambon) if filtered else []

        if filtered:
            return _rank(filtered, user_input, prefer_category, prefer_tambon)

    base = _strict_category_filter(base, prefer_category)
    ranked = _rank(base, user_input, prefer_category, prefer_tambon)
    ranked = _post_filter_results_by_query(ranked, user_input, prefer_category)
    return ranked

# ---------- Intent ----------
def _understand(user_input: str, history_text: str) -> dict:
    sys = (
        "คุณคือผู้ช่วยท้องถิ่นของอำเภอปะทิว จังหวัดชุมพร "
        "ตัดสินใจว่าผู้ใช้กำลังอยาก 'ค้นหาสถานที่' หรือ 'คุยทั่วไป'. "
        "ถ้าค้นหา ให้บอก category ที่ใกล้เคียงที่สุดจากหมวดทั่วไป เช่น "
        "คาเฟ่ ร้านอาหาร ที่พัก สถานที่ท่องเที่ยว ปั๊มน้ำมัน วัด ตลาด "
        "ร้านซ่อมรถ ร้านขายยา โรงยิม ธนาคาร มัสยิด สถานที่ราชการ ฯลฯ "
        "ถ้ามีตำบลในข้อความให้คืน tambon ด้วย (ถ้าไม่แน่ใจให้ null). "
        "ถ้ามี keyword สำคัญให้คืน keywords ด้วย. ตอบเฉพาะ JSON."
    )

    prompt = f"""{sys}
บริบทก่อนหน้า: {history_text or "(ไม่มี)"}
ผู้ใช้: "{user_input}"

ตอบเป็น JSON เท่านั้นในรูปแบบนี้:
{{
  "want_search": true,
  "category": "ร้านอาหาร",
  "tambon": null,
  "keywords": "ก๋วยเตี๋ยว"
}}
"""

    try:
        res = model.generate_content(prompt)
        data = _safe_json(getattr(res, "text", ""))
        return {
            "want_search": bool(data.get("want_search")),
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "keywords": data.get("keywords"),
        }
    except Exception as e:
        print(f"DEBUG: _understand error: {str(e)}")
        return {"want_search": False, "category": None, "tambon": None, "keywords": None}

def _reply_chitchat(user_input: str, history_text: str) -> str:
    prompt = (
        "คุณคือเพื่อนผู้ช่วยท้องถิ่นของอำเภอปะทิว ตอบสั้น สุภาพ อบอุ่น "
        f"บริบทก่อนหน้า:\n{history_text or '(ไม่มีประวัติ)'}\n\n"
        f"ผู้ใช้: {user_input}\nตอบ:"
    )
    try:
        res = model.generate_content(prompt)
        return (getattr(res, "text", "") or "").strip() or "ครับผม"
    except Exception as e:
        return f"ขออภัยครับ เกิดข้อผิดพลาดกับ AI: {str(e)}"

# ---------- Detection ----------
def _looks_like_followup(q: str) -> bool:
    q = q.strip().lower()
    return any(re.search(p, q) for p in FOLLOWUP_PATTERNS)

def _looks_like_map_request(q: str) -> bool:
    q = (q or "").strip().lower()
    keywords = ["แผนที่", "พิกัด", "ไปยังไง", "เส้นทาง", "ที่อยู่", "ไหนอะ", "ตรงไหน", "ขอแผนที่", "เปิดแผนที่"]
    return any(k in q for k in keywords)

def _looks_like_image_request(q: str) -> bool:
    q = (q or "").strip().lower()

    explicit_keywords = [
        "มีรูปไหม", "ขอรูป", "ดูรูป", "ดูภาพ", "มีภาพไหม",
        "ส่งรูป", "ขอภาพ", "รูปของ", "ภาพของ"
    ]
    if any(k in q for k in explicit_keywords):
        return True

    # คำว่า "รูป/ภาพ" เดี่ยวๆ มักเป็นคำค้นแนว "ถ่ายรูป" ไม่ควรตีเป็น follow-up ทันที
    if q in {"รูป", "ภาพ"}:
        return True

    return False

def _looks_like_photo_spot_query(q: str) -> bool:
    q = _norm(q)
    return any(k in q for k in PHOTO_SPOT_WORDS)

def _looks_like_choose_request(q: str) -> bool:
    q = q.strip().lower()
    phrases = ["เลือก", "ช่วยเลือก", "แนะนำ", "ร้านไหนดี", "ไหนดี", "เลือกสักร้าน", "เลือกให้หน่อย", "มีร้านแนะนำไหม"]
    return any(p in q for p in phrases)

def _looks_like_nearby_followup(q: str) -> bool:
    q = _norm(q)
    return any(k in q for k in NEARBY_WORDS)

def _extract_place_name(q: str) -> Optional[str]:
    s = q
    for w in [
        "เด่นอะไร", "เด่นที่อะไร", "เด่น", "แนะนำ", "signature", "ซิกเนเจอร์",
        "เปิดกี่โมง", "ปิดกี่โมง", "เวลา", "ทำการ",
        "ราคา", "ค่าเข้า", "ค่าธรรมเนียม", "งบ",
        "อยู่ไหน", "พิกัด", "แผนที่", "ไปยังไง", "เส้นทาง", "ที่อยู่",
        "ร้านนี้", "ที่นี่", "ตรงนี้", "สถานที่นี้",
        "รูป", "ภาพ", "มีรูปไหม", "ขอรูป", "ดูรูป", "ดูภาพ"
    ]:
        s = s.replace(w, "")
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s if len(s) >= 2 else None

def _text_to_category(txt: str) -> Optional[str]:
    t = _norm(txt)

    for c in CANON_CATS:
        if _norm(c) in t:
            return c

    scores = {}
    for cat, words in CATEGORY_SYNONYMS.items():
        score = sum(1 for w in words if _norm(w) in t)
        if score > 0:
            scores[cat] = score

    if scores:
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[0][0]

    for cat, words in LOCAL_CATEGORY_HINTS.items():
        if any(w in t for w in words):
            return cat

    return None

def _extract_ban_categories(user_input: str, last_results: List[Dict]) -> List[str]:
    t = _norm(user_input)
    if not any(w in t for w in NEG_WORDS):
        return []

    cat = _text_to_category(t)
    if cat:
        return [cat]

    if "ปิดหมด" in t or "ไม่เปิด" in t:
        if last_results:
            cats = [str(p.get("category") or "") for p in last_results]
            if cats:
                from collections import Counter
                mc = Counter([c for c in cats if c]).most_common(1)
                if mc:
                    guessed = _text_to_category(mc[0][0]) or mc[0][0]
                    return [guessed]
    return []

def _pick_focus_place(focus_place_id, last_results, maybe_name=None):
    if focus_place_id and last_results:
        for p in last_results:
            if p.get("id") == focus_place_id:
                return p

    if last_results and len(last_results) == 1:
        return last_results[0]

    if maybe_name:
        found = search_places(keywords_any=[maybe_name], limit=10)
        if not found:
            return None

        exact_matches = _find_exact_name_matches(maybe_name, found)
        if exact_matches:
            return exact_matches[0]

        best, score = None, -1
        for p in found:
            s = fuzz.partial_ratio(maybe_name.lower(), (p.get("name") or "").lower())
            if s > score:
                best, score = p, s
        return best

    return None

def _infer_intent_from_last_results(last_results: List[Dict]) -> Optional[str]:
    if not last_results:
        return None

    score_map = {}
    for p in last_results:
        cat = str(p.get("category") or "")
        for canon in CANON_CATS:
            if _category_matches_intent(cat, canon):
                score_map[canon] = score_map.get(canon, 0) + 1

    if not score_map:
        return None

    return sorted(score_map.items(), key=lambda x: x[1], reverse=True)[0][0]

def _format_place_answer_from_existing_fields(place: dict, user_q: str) -> str:
    name = place.get("name") or "สถานที่นี้"
    highlight = (place.get("highlight") or "").strip()
    desc = (place.get("description") or "").strip()
    category = (place.get("category") or "").strip()
    tambon = (place.get("tambon") or "").strip()
    lat, lng = place.get("latitude"), place.get("longitude")

    def has(x):
        return bool(x and str(x).lower() not in ["none", "null", "nan"])

    q = user_q.lower()
    parts = []

    if any(k in q for k in ["เด่น", "signature", "ซิกเนเจอร์", "แนะนำ"]):
        if has(highlight):
            parts.append(f"**จุดเด่นของ {name}:** {highlight}")
        elif has(desc):
            parts.append(f"{name} จุดเด่น/ภาพรวม: {desc[:220]}...")

    if any(k in q for k in ["อยู่ไหน", "พิกัด", "แผนที่", "ไปยังไง", "เส้นทาง", "ที่อยู่"]):
        line = []
        if has(category):
            line.append(f"ประเภท: {category}")
        if has(tambon):
            line.append(f"ตำบล: {tambon}")
        if lat and lng:
            line.append(f"พิกัด: {lat:.6f},{lng:.6f}")
        parts.append(" / ".join(line))

    if any(k in q for k in ["รูป", "ภาพ", "มีรูปไหม", "ขอรูป", "ดูรูป", "ดูภาพ"]):
        parts.append(f"นี่คือรูปหรือแผนที่ของ **{name}** ครับ")

    if not parts:
        summary = []
        if has(highlight):
            summary.append(f"จุดเด่น: {highlight}")
        if has(category):
            summary.append(f"ประเภท: {category}")
        parts.append(" / ".join(summary) or f"{name} ยังไม่มีรายละเอียดมากนักครับ")

    return "\n".join(parts)

def _score_for_choice(p: Dict, prefer_category: Optional[str]) -> int:
    s = 0
    if p.get("highlight"):
        s += min(60, len(str(p["highlight"])))
    if p.get("description"):
        s += min(60, len(str(p["description"])))
    if p.get("image_url"):
        s += 30
    if prefer_category and _is_allowed_for_intent(prefer_category, p):
        s += 25
    return s

def _reply_for_found_places(user_input: str, places: List[Dict], category: Optional[str]) -> str:
    if not places:
        return "ผมยังหาไม่เจอแบบตรงคำนี้ครับ แต่ลองบอกประเภทเพิ่มได้นะครับ"

    txt = _norm(user_input)
    detected_category = _infer_category_from_places(places)
    final_category = detected_category or category

    if final_category == "วัด" or any(w in txt for w in ["ทำบุญ", "ไหว้พระ", "วัด", "สำนักสงฆ์"]):
        return "ได้เลยครับ นี่คือสถานที่สำหรับทำบุญหรือไหว้พระที่ผมหามาให้ครับ"

    if final_category == "ร้านอาหาร" or any(w in txt for w in ["หิว", "กิน", "อาหาร", "ของกิน", "ร้านแนะนำ"]):
        return "ได้เลยครับ นี่คือร้านอาหารที่น่าลองในปะทิวครับ"

    if final_category == "คาเฟ่":
        return "ได้เลยครับ นี่คือคาเฟ่ที่น่าสนใจครับ"

    if _looks_like_photo_spot_query(user_input):
        return "ได้เลยครับ นี่คือสถานที่ที่เหมาะกับการถ่ายรูปในปะทิวครับ"

    if final_category == "ปั๊มน้ำมัน":
        return "ตอนนี้มีสถานที่ที่น่าจะตรงกับเรื่องเติมน้ำมันครับ"

    if final_category == "สถานที่ท่องเที่ยว":
        return "นี่คือสถานที่ท่องเที่ยวที่ผมหามาให้ครับ"

    if final_category == "ที่พัก":
        return "นี่คือที่พักที่ผมหามาให้ครับ"

    if final_category == "ร้านขายยา":
        return "นี่คือโรงพยาบาล คลินิก หรือร้านขายยาที่ผมหามาให้ครับ"

    if final_category == "โรงยิม":
        return "นี่คือยิมหรือฟิตเนสที่ผมหามาให้ครับ"

    if final_category == "ร้านตัดผม":
        return "นี่คือร้านตัดผมหรือร้านเสริมสวยที่ผมหามาให้ครับ"

    if final_category == "ตลาด":
        return "นี่คือตลาดที่ผมหามาให้ครับ"

    return "นี่คือสถานที่ที่ผมหามาให้ครับ มีที่ไหนถูกใจไหม?"

def _reply_for_nearby_found_places(reference_place: Dict, found_places: List[Dict], category: Optional[str]) -> str:
    ref_name = reference_place.get("name", "สถานที่นี้")
    if not found_places:
        return f"ผมยังไม่พบข้อมูลที่อยู่ใกล้ **{ref_name}** แบบตรงหมวดนี้ครับ"

    if category == "ที่พัก":
        return f"นี่คือที่พักที่อยู่ใกล้ **{ref_name}** ครับ"
    if category == "ร้านอาหาร":
        return f"นี่คือร้านอาหารที่อยู่ใกล้ **{ref_name}** ครับ"
    if category == "คาเฟ่":
        return f"นี่คือคาเฟ่ที่อยู่ใกล้ **{ref_name}** ครับ"
    if category == "ปั๊มน้ำมัน":
        return f"นี่คือปั๊มน้ำมันที่อยู่ใกล้ **{ref_name}** ครับ"
    if category == "ร้านขายยา":
        return f"นี่คือโรงพยาบาล คลินิก หรือร้านขายยาที่อยู่ใกล้ **{ref_name}** ครับ"

    return f"นี่คือสถานที่ใกล้ **{ref_name}** ที่ผมหามาให้ครับ"

def _search_near_reference_place(
    user_input: str,
    history_text: str,
    reference_place: Dict,
    banned_set: Set[str],
    within_km: float = 5.0,
) -> Tuple[str, List[Dict], List[str]]:
    ref_lat = reference_place.get("latitude")
    ref_lng = reference_place.get("longitude")

    if ref_lat is None or ref_lng is None:
        return ("ขออภัยครับ สถานที่อ้างอิงนี้ยังไม่มีพิกัด จึงยังหาแบบใกล้ๆ ไม่ได้ครับ", [], list(banned_set))

    u = _understand(user_input, history_text)
    guessed_cat = _forced_category_fallback(user_input) or _intent_from_keywords(user_input) or _local_guess_category(user_input)
    prefer_category = guessed_cat or u.get("category")

    if not prefer_category:
        return ("ได้ครับ อยากให้ผมหาสถานที่ประเภทไหนใกล้ๆ ที่นี่ เช่น ที่พัก ร้านอาหาร คาเฟ่ หรือโรงพยาบาลครับ", [], list(banned_set))

    nearby_keywords = _extract_keywords_for_nearby(user_input, u.get("keywords"), prefer_category)
    broad_query = _is_broad_query(user_input, nearby_keywords)

    base = search_places_nearby(
        ref_lat,
        ref_lng,
        category=prefer_category,
        tambon=None,
        keywords_any=None if broad_query else nearby_keywords,
        limit=30,
        within_km=within_km
    )

    base = _apply_banned(base, banned_set)

    filtered = [p for p in base if _is_allowed_for_intent(prefer_category, p)]
    if filtered:
        base = filtered

    base = _strict_category_filter(base, prefer_category)
    base = _post_filter_results_by_query(base, user_input, prefer_category)

    ref_id = reference_place.get("id")
    if ref_id is not None:
        base = [p for p in base if p.get("id") != ref_id]

    ranked = _rank(base, user_input, prefer_category, None)
    ranked = _post_filter_results_by_query(ranked, user_input, prefer_category)

    if not ranked:
        base2 = search_places_nearby(
            ref_lat,
            ref_lng,
            category=None,
            tambon=None,
            keywords_any=None,
            limit=30,
            within_km=within_km
        )
        base2 = _apply_banned(base2, banned_set)

        filtered2 = [p for p in base2 if _is_allowed_for_intent(prefer_category, p)]
        if filtered2:
            base2 = filtered2

        base2 = _strict_category_filter(base2, prefer_category)
        base2 = _post_filter_results_by_query(base2, user_input, prefer_category)

        if ref_id is not None:
            base2 = [p for p in base2 if p.get("id") != ref_id]

        ranked = _rank(base2, user_input, prefer_category, None)
        ranked = _post_filter_results_by_query(ranked, user_input, prefer_category)

    if not ranked:
        return (
            f"ผมยังไม่พบข้อมูลที่อยู่ใกล้ **{reference_place.get('name', 'สถานที่นี้')}** แบบตรงหมวดนี้ครับ "
            "แต่ถ้าต้องการ ผมช่วยหาหมวดใกล้เคียงให้แทนได้ครับ",
            [],
            list(banned_set)
        )

    reply = _reply_for_nearby_found_places(reference_place, ranked, prefer_category)
    return (reply, ranked, list(banned_set))

# ---------- Main ----------
def get_answer(
    user_input: str,
    user_lat: Optional[float] = None,
    user_lng: Optional[float] = None,
    history: Optional[List[Dict]] = None,
    focus_place_id: Optional[int] = None,
    last_results: Optional[List[Dict]] = None,
    banned_categories: Optional[List[str]] = None,
) -> Tuple[str, List[Dict], List[str]]:
    try:
        history = history or []
        history_text = _history_to_text(history, max_turns=8)
        last_results = last_results or []
        banned_set: Set[str] = set(banned_categories or [])

        newly_banned = _extract_ban_categories(user_input, last_results)
        banned_set.update(newly_banned)

        # 0) choose detection
        if _looks_like_choose_request(user_input):
            usable = _apply_banned(last_results, banned_set)

            prefer_cat = (
                _forced_category_fallback(user_input)
                or _intent_from_keywords(user_input)
                or _local_guess_category(user_input)
            )
            if not prefer_cat:
                prefer_cat = _infer_intent_from_last_results(last_results)
            if not prefer_cat:
                prefer_cat = "ร้านอาหาร"

            if usable:
                filtered_usable = [p for p in usable if _is_allowed_for_intent(prefer_cat, p)]
                candidate_pool = filtered_usable if filtered_usable else usable
                candidate_pool = _strict_category_filter(candidate_pool, prefer_cat)
                candidate_pool = _post_filter_results_by_query(candidate_pool, user_input, prefer_cat)

                if candidate_pool:
                    best = sorted(candidate_pool, key=lambda p: _score_for_choice(p, prefer_cat), reverse=True)[0]
                    name = best.get("name", "สถานที่นี้")
                    return (f"ผมขอแนะนำ **{name}** ครับ", [best], list(banned_set))

            base = _broader_category_fallback(
                user_input=user_input,
                user_lat=user_lat,
                user_lng=user_lng,
                prefer_tambon=None,
                prefer_category=prefer_cat,
                banned_set=banned_set
            )

            if base:
                best = base[0]
                name = best.get("name", "สถานที่นี้")
                return (f"ผมขอแนะนำ **{name}** ครับ", [best], list(banned_set))

            return (_fallback_reply(user_input, prefer_cat), [], list(banned_set))

        # 0.5) generic photo-spot query should be treated as search, not follow-up image request
        if _looks_like_photo_spot_query(user_input):
            pass
        # 1) follow-up / map / image
        elif _looks_like_followup(user_input) or _looks_like_map_request(user_input) or _looks_like_image_request(user_input):
            maybe_name = _extract_place_name(user_input)
            place = _pick_focus_place(focus_place_id, last_results, maybe_name)
            if place:
                if _looks_like_map_request(user_input):
                    return ("นี่ครับ แผนที่พิกัดของสถานที่", [place], list(banned_set))
                if _looks_like_image_request(user_input):
                    return (f"นี่คือรูปหรือแผนที่ของ **{place.get('name', 'สถานที่นี้')}** ครับ", [place], list(banned_set))
                return (_format_place_answer_from_existing_fields(place, user_input), [place], list(banned_set))

        # 2) nearby-followup from focused place
        maybe_named_place = _extract_place_name(user_input)
        focus_place = _pick_focus_place(focus_place_id, last_results, maybe_named_place)

        if _looks_like_nearby_followup(user_input) and focus_place:
            return _search_near_reference_place(
                user_input=user_input,
                history_text=history_text,
                reference_place=focus_place,
                banned_set=banned_set,
                within_km=5.0
            )

        # 2.5) exact place-name match first
        if _looks_like_explicit_place_name_query(user_input):
            q_compact = _normalize_loose_text(user_input)
            exact_candidates = search_places(
                category=None,
                tambon=None,
                keywords_any=[user_input, q_compact],
                limit=50
            )
            exact_candidates = _apply_banned(exact_candidates, banned_set)

            exact_matches = _find_exact_name_matches(user_input, exact_candidates)
            if exact_matches:
                ranked_exact = _rank(exact_matches, user_input, None, None, top_k=5)
                return ("นี่คือสถานที่ที่คุณค้นหาครับ", ranked_exact[:1], list(banned_set))

        # 3) intent logic from LLM
        u = _understand(user_input, history_text)

        # 4) stronger heuristics
        guessed_cat = (
            _forced_category_fallback(user_input)
            or _intent_from_keywords(user_input)
            or _local_guess_category(user_input)
        )
        txt = user_input.lower()

        if not u.get("want_search") and guessed_cat:
            u["want_search"] = True
            u["category"] = guessed_cat

        if not u.get("want_search"):
            if any(w in txt for w in [
                "ชา", "กาแฟ", "ข้าว", "อาหาร", "หิว", "กิน", "ของกิน", "ปั๊ม",
                "เที่ยว", "ที่พัก", "โรงแรม", "รีสอร์ท", "ยิม", "วัด", "ตลาด", "ยา",
                "โรงพยาบาล", "คลินิก", "อนามัย", "น้ำ", "เครื่องดื่ม", "น้ำปั่น",
                "ตัดผม", "เสริมสวย", "บาร์เบอร์", "ทำบุญ", "ไหว้พระ", "ทะเล", "ชายหาด", "หาด", "อ่าว",
                "ถ่ายรูป", "ถ่ายภาพ", "มุมถ่ายรูป", "จุดถ่ายรูป", "วิวสวย"
            ]):
                u["want_search"] = True
                u["category"] = guessed_cat or "สถานที่ท่องเที่ยว"

        if not u.get("want_search"):
            return (_reply_chitchat(user_input, history_text), [], list(banned_set))

        # 5) Search
        prefer_category = guessed_cat or u.get("category")
        prefer_tambon = u.get("tambon")
        keywords = _extract_keywords(user_input, u.get("keywords"))
        broad_query = _is_broad_query(user_input, keywords)

        base = _search_by_context(
            user_input=user_input,
            user_lat=user_lat,
            user_lng=user_lng,
            prefer_tambon=prefer_tambon,
            keywords=None if broad_query else keywords,
            prefer_category=prefer_category,
            limit=30
        )

        base = _apply_banned(base, banned_set)

        if prefer_category:
            filtered_by_intent = [p for p in base if _is_allowed_for_intent(prefer_category, p)]
            if filtered_by_intent:
                base = filtered_by_intent

        base = _strict_category_filter(base, prefer_category)
        base = _post_filter_results_by_query(base, user_input, prefer_category)

        if not base and keywords:
            base = _search_by_context(
                user_input=user_input,
                user_lat=user_lat,
                user_lng=user_lng,
                prefer_tambon=prefer_tambon,
                keywords=None,
                prefer_category=prefer_category,
                limit=30
            )
            base = _apply_banned(base, banned_set)

            if prefer_category:
                filtered_by_intent = [p for p in base if _is_allowed_for_intent(prefer_category, p)]
                if filtered_by_intent:
                    base = filtered_by_intent

            base = _strict_category_filter(base, prefer_category)
            base = _post_filter_results_by_query(base, user_input, prefer_category)

        ranked = _rank(base, user_input, prefer_category, prefer_tambon)
        ranked = _post_filter_results_by_query(ranked, user_input, prefer_category)

        if not ranked and keywords:
            base2 = _search_by_context(
                user_input=user_input,
                user_lat=user_lat,
                user_lng=user_lng,
                prefer_tambon=prefer_tambon,
                keywords=keywords,
                prefer_category=prefer_category,
                limit=30
            )
            base2 = _apply_banned(base2, banned_set)

            if prefer_category:
                filtered_by_intent = [p for p in base2 if _is_allowed_for_intent(prefer_category, p)]
                if filtered_by_intent:
                    base2 = filtered_by_intent

            base2 = _strict_category_filter(base2, prefer_category)
            base2 = _post_filter_results_by_query(base2, user_input, prefer_category)

            ranked = _rank(base2, user_input, prefer_category, prefer_tambon)
            ranked = _post_filter_results_by_query(ranked, user_input, prefer_category)

        # 6) broader fallback by category/context
        if not ranked:
            broader = _broader_category_fallback(
                user_input=user_input,
                user_lat=user_lat,
                user_lng=user_lng,
                prefer_tambon=prefer_tambon,
                prefer_category=prefer_category,
                banned_set=banned_set
            )

            if broader:
                reply = _fallback_reply(user_input, prefer_category)
                return (reply, broader[:8], list(banned_set))

        # 7) final fallback message (no hard fail)
        if not ranked:
            return (_fallback_reply(user_input, prefer_category), [], list(banned_set))

        reply = _reply_for_found_places(user_input, ranked, prefer_category)
        return (reply, ranked, list(banned_set))

    except Exception as e:
        return (
            f"เกิดข้อผิดพลาดในการประมวลผล: {str(e)}",
            [],
            (banned_categories or [])
        )