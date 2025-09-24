import json
from typing import List, Dict, Tuple

import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places

# ----- ตั้งค่า LLM -----
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)


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
คุณคือระบบช่วยหาสถานที่ในอำเภอปะทิว จังหวัดชุมพร
หน้าที่: วิเคราะห์คำถามผู้ใช้แล้วสรุปเป็น JSON เท่านั้น ห้ามมีคำอธิบายอื่น

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


def _format_one_place(p: Dict) -> str:
    name = p.get("name") or "-"
    tambon = p.get("tambon") or "-"
    cat = p.get("category") or ""
    desc = (p.get("description") or "").strip()
    hi = (p.get("highlight") or "").strip()
    lat = p.get("latitude")
    lng = p.get("longitude")

    lines = [f"• {name} ({cat}) – ตำบล{tambon}"]
    if desc:
        lines.append(desc)
    if hi:
        lines.append(f"จุดเด่น: {hi}")
    if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
        map_link = f"https://www.google.com/maps?q={lat},{lng}"
        lines.append(f"🗺️ พิกัด: {lat:.6f}, {lng:.6f}  |  [เปิดแผนที่]({map_link})")
    return "\n".join(lines)


def get_answer(user_input: str) -> Tuple[str, List[Dict]]:
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon = analysis.get("tambon")
    keywords = analysis.get("keywords")

    results = search_places(category=category, tambon=tambon, keywords=keywords, limit=10)

    # ---- กรองผลลัพธ์ด้วย keywords แบบเข้มงวด ----
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

    if not (category or tambon or keywords):
        return ("ผมยังไม่เข้าใจชัด ลองพิมพ์เพิ่ม เช่น “ตลาดเลริวเซ็น ชุมโค” นะครับ 😊", [])

    if not results:
        msg = f"ยังไม่พบ{category or 'สถานที่'}"
        if tambon:
            msg += f"ในตำบล{tambon}"
        if keywords:
            msg += f" ที่เกี่ยวกับ {keywords}"
        msg += " ตอนนี้เลยครับ ลองเปลี่ยนคำค้นนิดนึงก็ได้ครับ"
        return (msg, [])

    intro = "เจอที่น่าสนใจให้ครับ:\n\n"
    body = "\n\n".join(_format_one_place(p) for p in results)
    outro = "\n\nอยากให้ปักหมุดเส้นทาง หรือกรองเพิ่ม (เช่น เมนู/งบประมาณ) บอกผมได้เลยครับ"
    return (intro + body + outro, results)
