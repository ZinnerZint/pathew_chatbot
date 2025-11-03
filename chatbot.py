# chatbot.py — logic: ตำบลก่อน ประเภททีหลัง, ครอบคลุมทุกสถานที่, มีโหมดถามต่อ
# พร้อมแสดงผลข้อความ + การ์ดใน app.py ได้สมบูรณ์

import json, re
from typing import List, Dict, Tuple, Optional
import google.generativeai as genai
from rapidfuzz import fuzz
from config import GEMINI_API_KEY
from db import search_places, search_places_nearby

# ---------- ตั้งค่าโมเดล ----------
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

# ---------- กลุ่มคำที่ใช้ตรวจ ----------
STOP_WORDS = {"อยาก","ช่วย","หน่อย","แถว","ที่","มี","ไหม","มั้ย","ครับ","ค่ะ","คับ","จ้า","นะ","บ้าง","ขอ","หา","ด้วย","เอา","หนึ่ง","นึง","แนะนำ","ตรง","แถวไหน","ขอหน่อย"}
TAMBONS = ["ชุมโค","บางสน","ปากคลอง","เขาไชยราช","บางหมาก","สะพลี","ทะเลทรัพย์","ปะทิว"]

CATEGORY_HINTS = {
    "ร้านอาหาร": {"อาหาร","กิน","ข้าว","ซีฟู้ด","ก๋วยเตี๋ยว","กับข้าว","ร้าน"},
    "คาเฟ่": {"คาเฟ่","กาแฟ","ชา","ของหวาน","เบเกอรี่","ชานม"},
    "สถานที่ท่องเที่ยว": {"เที่ยว","ที่เที่ยว","อ่าว","หาด","ชายหาด","ทะเล","จุดชมวิว"},
    "ตลาด": {"ตลาด","ตลาดสด","ตลาดนัด"},
    "วัด": {"วัด","ไหว้พระ","ทำบุญ"},
    "ที่พัก": {"ที่พัก","รีสอร์ท","โฮมสเตย์","โรงแรม"},
    "ปั๊มน้ำมัน": {"ปั๊ม","เติมน้ำมัน","บางจาก","เชลล์","พีที","ptt"},
    "ร้านซ่อมรถ": {"อู่","ซ่อม","ซ่อมรถ","ปะยาง","ยาง","แบตเตอรี่"},
    "ยิม/ฟิตเนส": {"ยิม","ฟิตเนส","ออกกำลังกาย","เวท"},
}

# ---------- ฟังก์ชันช่วย ----------
def _norm(s): return (s or "").strip().lower()
def _guess_tambon(text:str)->Optional[str]:
    for t in TAMBONS:
        if t in text: return t
    return None
def _guess_category(text:str)->Optional[str]:
    for cat, kws in CATEGORY_HINTS.items():
        if any(k in text for k in kws): return cat
    return None
def _extract_keywords(user_input:str)->List[str]:
    parts = re.split(r"[, ]+", user_input)
    return [p for p in parts if p and p not in STOP_WORDS]
def _rank(rows:List[Dict], query:str)->List[Dict]:
    q=_norm(query); out=[]
    for r in rows:
        blob=" ".join(str(v) for v in r.values()).lower()
        score=fuzz.partial_ratio(q,blob)
        if q in blob: score+=10
        out.append((score,r))
    return [r for _,r in sorted(out,key=lambda x:x[0],reverse=True)]
def _filter_by_keywords(rows,keywords):
    if not keywords:return rows
    result=[]
    for r in rows:
        blob=" ".join([str(r.get("name","")),str(r.get("description","")),str(r.get("highlight","")),str(r.get("category",""))]).lower()
        if any(k in blob for k in keywords): result.append(r)
    return result

# ---------- ส่วนตอบโต้ ----------
def get_answer(user_input:str,
               user_lat:Optional[float]=None,
               user_lng:Optional[float]=None,
               history:Optional[List[Dict]]=None,
               focus_place_id=None,
               last_results=None)->Tuple[str,List[Dict]]:

    text=_norm(user_input)
    tambon=_guess_tambon(text)
    category=_guess_category(text)
    keywords=_extract_keywords(text)

    # ---- โหมดถามต่อ ----
    if any(k in text for k in ["เด่น","อยู่ไหน","แผนที่","เวลา","เปิด","ปิด","ราคา","ค่าเข้า"]):
        if not last_results:
            return ("ยังไม่มีข้อมูลสถานที่ก่อนหน้านี้เลยครับ ลองบอกชื่อสถานที่มาก็ได้ เช่น “ตลาดเลริวเซ็น”", [])
        place=last_results[0]
        name=place.get("name","สถานที่นี้")
        highlight=place.get("highlight") or place.get("description") or ""
        return (f"{name} จุดเด่นคือ {highlight[:200]}{'...' if len(highlight)>200 else ''}", [])

    # ---- ขั้นตอนค้นหา ----
    # 1 มีตำบล + หมวด
    if tambon and category:
        base=search_places(category=category,tambon=tambon,limit=40)
        ranked=_filter_by_keywords(_rank(base,text),keywords)
        if ranked:
            msg=f"สถานที่ประเภท{category}ในตำบล{tambon}ที่น่าสนใจครับ"
            return (msg,ranked)

    # 2 มีแค่ตำบล
    if tambon and not category:
        base=search_places(category=None,tambon=tambon,limit=40)
        ranked=_rank(base,text)
        if ranked:
            return (f"นี่คือสถานที่ในตำบล{tambon}ครับ",ranked)

    # 3 มีหมวดแต่ไม่มีตำบล
    if category and not tambon:
        base=search_places(category=category,tambon=None,limit=40)
        ranked=_filter_by_keywords(_rank(base,text),keywords)
        if ranked:
            return (f"สถานที่{category}ในอำเภอปะทิวที่น่าสนใจครับ",ranked)

    # 4 ไม่มีทั้งคู่แต่มีพิกัด
    if user_lat and user_lng:
        base=search_places_nearby(user_lat,user_lng,limit=30,within_km=20)
        ranked=_filter_by_keywords(_rank(base,text),keywords)
        if ranked:
            return ("นี่คือสถานที่ใกล้คุณมากที่สุดครับ",ranked)

    # 5 fallback — ทั้งอำเภอ
    base=search_places(category=None,tambon=None,limit=50)
    ranked=_filter_by_keywords(_rank(base,text),keywords)
    if ranked:
        return ("ลองดูสถานที่ที่เกี่ยวข้องในอำเภอปะทิวครับ",ranked)

    # ไม่เจอเลย
    return (f"ยังไม่พบสถานที่ที่ตรงกับ “{user_input}” ครับ ลองระบุชื่อหมวดหรือชื่อตำบลเพิ่มได้ครับ", [])
