# app.py (เฉพาะบรรทัดที่สำคัญ)
import streamlit as st
import google.generativeai as genai
from rag_db import search_relevant_places, PATHIO_TAMBONS, ensure_schema

genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
st.set_page_config(page_title="TripTech AI – Pathio Guide", page_icon="🌴")
st.title("🌴 TripTech AI – ไกด์รุ่นพี่ประจำอำเภอปะทิว")

# ครั้งแรกหรือทุกครั้งที่รัน: ให้แน่ใจว่ามี schema
ensure_schema()

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("อยากหาอะไรในปะทิว ถามมาได้เลย…")

def build_prompt(history_text: str, context: str) -> str:
    tambon_text = ", ".join(PATHIO_TAMBONS)
    return f"""
คุณคือไกด์รุ่นพี่ที่แนะนำสถานที่ใน "อำเภอปะทิว จังหวัดชุมพร" เท่านั้น
ตำบลที่ให้ข้อมูลได้มี: {tambon_text}

ข้อกำหนดสำคัญ:
- ตอบเป็นคำบรรยายสั้น กระชับ สำนวนสุภาพแบบพี่แนะนำรุ่นน้อง
- หลีกเลี่ยงการสรุปเป็นข้อ/หัวข้อย่อย
- อย่าทักทายซ้ำถ้าไม่ใช่ประโยคแรก
- ถ้าผู้ใช้ถามนอกพื้นที่ ให้บอกขอบเขตอย่างสุภาพ และชวนให้ระบุใน 8 ตำบลของปะทิว

บทสนทนาก่อนหน้า:
{history_text}

ข้อมูลอ้างอิงสถานที่ (RAG):
{context}

จงตอบเฉพาะคำถามล่าสุด ต่อเนื่องจากบทสนทนาเดิม
ห้ามใส่หัวข้อย่อย ให้เป็นย่อหน้าสั้น ๆ สไตล์ไกด์รุ่นพี่เท่านั้น
"""

if user_input:
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # ✅ ดึงจาก PostgreSQL
    results = search_relevant_places(user_input, top_k=6)

    # สร้าง context ให้สั้นกระชับ
    lines = []
    for r in results:
        line = f"- {r['ชื่อสถานที่']} • ตำบล {r['ตำบล']} :: {r.get('คำอธิบาย','')}"
        if r.get("จุดเด่น"):
            line += f" • จุดเด่น: {r['จุดเด่น']}"
        lines.append(line)
    context = "\n".join(lines) if lines else "— ไม่เจอในขอบเขตปะทิวจากฐานข้อมูล —"

    # รวมประวัติแชท
    history_text = ""
    for m in st.session_state.messages:
        role = "ผู้ใช้" if m["role"] == "user" else "AI"
        history_text += f"{role}: {m['content']}\n"

    prompt = build_prompt(history_text, context)

    try:
        model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")
        response = model.generate_content(prompt)
        bot_reply = (response.text or "").strip() or "ลองระบุตำบลหรือประเภทสถานที่เพิ่มเติมหน่อยนะครับ"
    except Exception as e:
        bot_reply = f"❌ เกิดข้อผิดพลาดจาก Gemini: {e}"

    st.chat_message("assistant").markdown(bot_reply)
    st.session_state.messages.append({"role": "assistant", "content": bot_reply})

    # แสดงรูป (ถ้ามี)
    for r in results:
        img = r.get("รูปภาพ", "")
        if isinstance(img, str) and img.startswith(("http://", "https://")):
            st.image(img, caption=r.get("ชื่อสถานที่", ""), use_container_width=True)
