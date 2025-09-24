import google.generativeai as genai
from config import GEMINI_API_KEY
from db import search_places
from random import choice

# ตั้งค่า Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-lite")


def analyze_query(user_input: str) -> dict:
    """
    ใช้ Gemini วิเคราะห์คำถามผู้ใช้
    return: dict เช่น {"category": "ร้านอาหาร", "tambon": "บางสน", "price": "ถูก"}
    """
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
    """
    วิเคราะห์คำถาม → query DB → ตอบเป็นประโยคบรรยาย
    """
    analysis = analyze_query(user_input)
    category = analysis.get("category")
    tambon = analysis.get("tambon")
    price = analysis.get("price")

    if not (category or tambon or price):
        return "ตอนนี้ผมยังจับใจความไม่ได้ครับ ลองพิมพ์ใหม่ เช่น 'ร้านอาหารราคาถูกแถวบางสน' จะชัดขึ้นครับ 🙂"

    # ดึงข้อมูลจาก DB
    results = search_places(category=category, tambon=tambon, limit=5)

    if results:
        place = choice(results)  # เลือกมา 1 ที่เพื่อบรรยาย
        reply = f"{place['name']} อยู่ที่ตำบล {place['tambon']} "
        if place.get("description"):
            reply += f"{place['description']} "
        if place.get("highlight"):
            reply += f"จุดเด่นคือ {place['highlight']} "
        if price:
            reply += f"ราคาก็ถือว่า {price} ครับ"
        return reply.strip()
    else:
        return f"ยังไม่พบ {category or 'สถานที่'} ในตำบล {tambon or 'พื้นที่นี้'} ครับ"
