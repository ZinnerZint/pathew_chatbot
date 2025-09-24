import json
from typing import List, Dict, Tuple, Optional

import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places

# ----- ตั้งค่า LLM -----
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash-lite"
model = genai.GenerativeModel(MODEL_NAME)


def _safe_json(text: str) -> dict:
    """
    พยายามดึง JSON ออกจากคำตอบของโมเดล
    รองรับเคสที่ LLM ใส่ ```json ... ```
    """
    if not text:
        return {}
    t = text.strip()
    # ตัด code fences ออกถ้ามี
    if t.startswith("```"):
        t = t.strip("`")
        # ลบชนิดภาษาออก เช่น json\n
        t = "\n".join(t.split("\n")[1:])
    try:
        return json.loads(t)
    except Exception:
        return {}


def analyze_query(user_input: str) -> dict:
    """
    ใช้ Gemini วิเคราะห์ intent → {"category": "...", "tambon": "...", "price": "...", "keywords": "..."}
    """
    prompt = f"""
คุณคือระบบช่วยหาสถานที่ในอำเภอปะทิว จังหวัดชุมพร
หน้าที่: วิเคราะห์คำถามผู้ใช้แล้วสรุปเป็น JSON เท่านั้น ห้ามมีคำอธิบายอื่น

ผู้ใช้: "{user_input}"

จงตอบเป็น JSON โครงสร้างนี้เท่านั้น:
{{
  "category": "ประเภทสถานที่ เช่น ร้านอาหาร/คาเฟ่/ปั๊มน้ำมัน (ไม่รู้ให้ใส่ null)",
  "tambon": "ชื่อตำบลในอำเภอปะทิว (ไม่รู้ให้ใส่ null)",
  "price": "ถูก/ปานกลาง/แพง (ถ้ามี ไม่รู้ให้ใส่ null)",
  "keywords": "คำค้นเพิ่ม เช่น เมนู/บรรยากาศ (ไม่มีให้ใส่ null)"
}}
"""
    try:
        res = model.generate_content(prompt)
        data = _safe_json(res.text)
        # ป้องกันคีย์หาย
        return {
            "category": data.get("category"),
            "tambon": data.get("tambon"),
            "price": data.get("price"),
            "keywords": data.get("keywords"),
        }
    except Exception:
        return {"category": None, "tambon": None, "price": None, "keywords": None}


def _format_one_place(p: Dict) -> str:
    """สรุป 1 สถานที่ให้เป็นข้อความบรรยายสั้นๆ"""
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
    """
    วิเคราะห์ → ค้น DB → สร้างคำตอบสวยๆ
    return (ข้อความตอบ, รายการสถานที่ที่ดึงได้)
    """
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon = analysis.get("tambon")
    keywords = analysis.get("keywords")

    # ถ้า LLM วิเคราะห์ได้ไม่พอ ลองค้นแบบกว้างๆ ด้วย category/tambon เฉยๆ
    results = search_places(category=category, tambon=tambon, limit=5)

    # ถ้าอยากแม่นขึ้นอีกนิด ใช้ keywords มาช่วยกรองฝั่ง Python (ไม่บังคับ)
    if keywords and isinstance(keywords, str):
        kw = keywords.lower()
        def ok(row):
            text = " ".join([
                str(row.get("name") or ""),
                str(row.get("description") or ""),
                str(row.get("highlight") or ""),
            ]).lower()
            return all(k.strip() in text for k in kw.split() if k.strip())
        filtered = list(filter(ok, results))
        if filtered:
            results = filtered

    if not (category or tambon):
        return ("ผมยังระบุประเภท/ตำบลไม่ชัด ลองพิมพ์เช่น “ร้านอาหารราคาถูกแถวบางสน” นะครับ 😊", [])

    if not results:
        msg = f"ยังไม่พบ{category or 'สถานที่'}"
        if tambon:
            msg += f"ในตำบล{tambon}"
        msg += " ตอนนี้เลยครับ ลองเปลี่ยนคำค้นนิดนึงก็ได้ครับ"
        return (msg, [])

    # ทำคำตอบแบบรวมหลายที่
    intro = "เจอที่น่าสนใจให้ครับ:\n\n"
    body = "\n\n".join(_format_one_place(p) for p in results)
    outro = "\n\nอยากให้ปักหมุดเส้นทาง หรือกรองเพิ่ม (เช่น เมนู/งบประมาณ) บอกผมได้เลยครับ"
    return (intro + body + outro, results)
