import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places   # <-- ใช้ DB แทน mock
from random import choice

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")

def analyze_query(user_input: str) -> dict:
    prompt = f"""
    คุณคือระบบช่วยหาสถานที่ในอำเภอปะทิว จังหวัดชุมพร
    ผู้ใช้พิมพ์ว่า: "{user_input}"
    จงวิเคราะห์แล้วส่งออกในรูป JSON เท่านั้น:
    {{
      "category": "...",
      "tambon": "...",
      "price": "..."
    }}
    ถ้าไม่มีข้อมูลบางอย่างให้ใส่ null
    """
    response = model.generate_content(prompt)
    try:
        import json
        return json.loads(response.text)
    except:
        return {"category": None, "tambon": None, "price": None}

def get_answer(user_input: str):
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon = analysis.get("tambon")
    price = analysis.get("price")

    if not (category or tambon or price):
        return "ผมยังไม่ค่อยเข้าใจคำถาม ลองพิมพ์ใหม่อีกที เช่น 'ร้านอาหารราคาถูกแถวบางสน' นะครับ 🙂"

    results = search_places(category=category, tambon=tambon, limit=5)

    if results:
        place = choice(results)  # สุ่มเลือกมาบรรยาย
        reply = f"{place['name']} อยู่ที่ตำบล {place['tambon']} "
        if place.get("description"):
            reply += f"{place['description']} "
        if place.get("highlight"):
            reply += f"จุดเด่นคือ {place['highlight']} "
        if price:
            reply += f"ราคาก็ถือว่า {price} ครับ"
        return reply.strip()
    else:
        return f"ยังไม่พบ {category or 'สถานที่'} ในตำบล {tambon or 'นี้'} ครับ"
