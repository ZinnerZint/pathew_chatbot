import streamlit as st
from chatbot import get_answer

st.set_page_config(page_title="🤖 Pathew Chatbot", page_icon="🌴")
st.title("🤖 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว")

user_input = st.text_input("คุณอยากหาสถานที่อะไร? (เช่น ร้านอาหารราคาถูกแถวบางสน)")

if st.button("ค้นหา"):
    if user_input:
        answer = get_answer(user_input)
        st.write(answer)
    else:
        st.warning("กรุณาพิมพ์คำถามก่อนครับ")
