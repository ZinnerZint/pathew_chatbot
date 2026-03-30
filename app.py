import json
import re
from urllib.parse import quote, urlparse, parse_qs

import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Pathew Chatbot",
    page_icon="P",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
.example-bubbles {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 6px;
}

.example-bubble {
    padding: 10px 12px;
    border-radius: 14px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(128,128,128,0.22);
    font-size: 0.92rem;
    line-height: 1.45;
}

.block-container {
    padding-top: 1rem;
    padding-bottom: 1.2rem;
}

.hero-box {
    padding: 1rem 1.2rem;
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 16px;
    margin-bottom: 1rem;
}

.small-note {
    font-size: 0.92rem;
    opacity: 0.9;
}

.empty-box {
    border: 1px dashed rgba(128,128,128,0.35);
    border-radius: 14px;
    padding: 18px;
    text-align: center;
    opacity: 0.9;
}

.chat-bubble-wrap {
    display: flex;
    width: 100%;
    margin-bottom: 10px;
}

.chat-bubble-wrap.user {
    justify-content: flex-end;
}

.chat-bubble-wrap.assistant {
    justify-content: flex-start;
}

.chat-bubble {
    max-width: 85%;
    padding: 12px 14px;
    border-radius: 16px;
    line-height: 1.55;
    font-size: 0.98rem;
    border: 1px solid rgba(128,128,128,0.22);
    word-wrap: break-word;
}

.chat-bubble.user {
    background: rgba(59, 130, 246, 0.16);
}

.chat-bubble.assistant {
    background: rgba(255, 255, 255, 0.04);
}

.chat-name {
    font-size: 0.78rem;
    opacity: 0.75;
    margin-bottom: 4px;
    font-weight: 600;
}

.place-card {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 16px;
    padding: 12px;
    margin-bottom: 12px;
}

.place-title {
    font-size: 1.6rem;
    font-weight: 800;
    margin-bottom: 0.35rem;
    line-height: 1.2;
}

.place-meta {
    font-size: 0.92rem;
    opacity: 0.9;
    margin-bottom: 0.7rem;
}

.place-desc {
    line-height: 1.6;
    margin-bottom: 0.8rem;
}

.place-highlight {
    border-left: 4px solid #3b82f6;
    padding-left: 10px;
    margin-top: 8px;
    margin-bottom: 10px;
}

.sidebar-note {
    font-size: 0.92rem;
    opacity: 0.92;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================
st.markdown("""
<div class="hero-box">
    <h2 style="margin:0 0 6px 0;">AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h2>
    <div class="small-note">
        ค้นหาร้านอาหาร คาเฟ่ ที่พัก สถานที่ท่องเที่ยว ปั๊มน้ำมัน ร้านขายยา และสถานที่สำคัญในอำเภอปะทิว
    </div>
</div>
""", unsafe_allow_html=True)


# =========================================================
# AVATAR
# =========================================================
svg_user = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
<circle cx='20' cy='20' r='18' fill='#2563EB'/></svg>"""
svg_bot = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
<circle cx='20' cy='20' r='18' fill='#10B981'/></svg>"""

avatar_user = f"data:image/svg+xml;utf8,{quote(svg_user)}"
avatar_bot = f"data:image/svg+xml;utf8,{quote(svg_bot)}"


# =========================================================
# HELPERS
# =========================================================
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass


def extract_google_drive_file_id(url: str):
    if not url or not isinstance(url, str):
        return None

    m = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)

    if "open?id=" in url:
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)
            file_ids = q.get("id")
            if file_ids:
                return file_ids[0]
        except Exception:
            pass

    if "uc?id=" in url:
        try:
            parsed = urlparse(url)
            q = parse_qs(parsed.query)
            file_ids = q.get("id")
            if file_ids:
                return file_ids[0]
        except Exception:
            pass

    return None


def fix_image_url(url: str):
    if not url or not isinstance(url, str):
        return None

    url = url.strip()
    if not url:
        return None

    if "drive.google.com" in url:
        file_id = extract_google_drive_file_id(url)
        if file_id:
            return f"https://drive.google.com/uc?export=view&id={file_id}"
        return url

    if "lh3.google" in url or "googleusercontent.com" in url:
        if "=" not in url.split("/")[-1]:
            return f"{url}=s1200"
        return url

    return url


def parse_image_urls(raw_value):
    if not raw_value:
        return []

    if isinstance(raw_value, list):
        return [fix_image_url(u) for u in raw_value if isinstance(u, str) and u.strip()]

    if isinstance(raw_value, str):
        txt = raw_value.strip()
        if not txt:
            return []

        try:
            data = json.loads(txt)
            if isinstance(data, list):
                return [fix_image_url(u) for u in data if isinstance(u, str) and u.strip()]
        except Exception:
            pass

        return [fix_image_url(txt)]

    return []


def get_best_image_candidates(place: dict):
    urls = []

    image_urls = parse_image_urls(place.get("image_urls"))
    urls.extend(image_urls)

    image_url = place.get("image_url")
    if isinstance(image_url, str) and image_url.strip():
        fixed = fix_image_url(image_url)
        if fixed and fixed not in urls:
            urls.append(fixed)

    clean = []
    for u in urls:
        if isinstance(u, str) and u.startswith(("http://", "https://")):
            clean.append(u)

    return clean


def build_static_map_url(lat, lng):
    if lat is None or lng is None or not MAPS_API_KEY:
        return None

    return (
        "https://maps.googleapis.com/maps/api/staticmap"
        f"?center={lat},{lng}"
        f"&zoom=15"
        f"&size=900x520"
        f"&maptype=roadmap"
        f"&markers=color:red%7C{lat},{lng}"
        f"&key={MAPS_API_KEY}"
    )


def try_show_image(url: str, caption: str = None):
    if not url:
        return False
    try:
        st.image(url, caption=caption, use_container_width=True)
        return True
    except Exception:
        return False


def render_chat_bubble(role: str, content: str):
    wrapper_class = "user" if role == "user" else "assistant"
    label = "คุณ" if role == "user" else "ผู้ช่วย"

    st.markdown(
        f"""
        <div class="chat-bubble-wrap {wrapper_class}">
            <div class="chat-bubble {wrapper_class}">
                <div class="chat-name">{label}</div>
                <div>{content}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SESSION STATE
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "สวัสดีครับ อยากหาสถานที่แบบไหนในอำเภอปะทิว บอกผมได้เลยครับ"
        }
    ]

if "user_lat" not in st.session_state:
    st.session_state.user_lat = None

if "user_lng" not in st.session_state:
    st.session_state.user_lng = None

if "focus_place_id" not in st.session_state:
    st.session_state.focus_place_id = None

if "last_results" not in st.session_state:
    st.session_state.last_results = []

if "banned_categories" not in st.session_state:
    st.session_state.banned_categories = []


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown("**ตัวอย่างคำถาม**")
    st.markdown("""
    <div class="example-bubbles">
        <div class="example-bubble">มีร้านอาหารแนะนำไหม</div>
        <div class="example-bubble">ขอคาเฟ่ในปะทิว</div>
        <div class="example-bubble">ขอที่พักในชุมโค</div>
        <div class="example-bubble">มีสถานที่ท่องเที่ยวในสะพลีไหม</div>
        <div class="example-bubble">บ้านต้นไม้อวดชุมเด่นอะไร</div>
        <div class="example-bubble">ขอแผนที่ของถ้ำเขาไชย</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("ล้างผลลัพธ์ล่าสุด", use_container_width=True):
        st.session_state["last_results"] = []
        st.session_state["focus_place_id"] = None
        safe_rerun()

    if st.button("เริ่มแชทใหม่", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "สวัสดีครับ อยากหาสถานที่แบบไหนในอำเภอปะทิว บอกผมได้เลยครับ"
            }
        ]
        st.session_state["last_results"] = []
        st.session_state["focus_place_id"] = None
        st.session_state["banned_categories"] = []
        safe_rerun()


# =========================================================
# PLACE CARD
# =========================================================
def _render_place_card(p: dict):
    name = p.get("name", "-")
    desc = (p.get("description") or "").strip()
    hi = (p.get("highlight") or "").strip()
    tambon = p.get("tambon", "-")
    category = p.get("category", "-")
    lat = p.get("latitude")
    lng = p.get("longitude")

    map_link = None
    if lat is not None and lng is not None:
        map_link = f"https://www.google.com/maps?q={lat},{lng}"

    with st.container(border=True):
        img_col, info_col = st.columns([1, 1.45], gap="medium")

        with img_col:
            shown = False
            image_candidates = get_best_image_candidates(p)

            if image_candidates:
                shown = try_show_image(image_candidates[0])

            if not shown:
                static_map = build_static_map_url(lat, lng)
                if static_map:
                    shown = try_show_image(static_map)

            if not shown:
                st.info("ไม่มีรูปภาพ")

        with info_col:
            st.markdown(f'<div class="place-title">{name}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="place-meta">ประเภท: {category} | ตำบล: {tambon}</div>',
                unsafe_allow_html=True
            )

            if "distance_km" in p and p.get("distance_km") is not None:
                try:
                    st.markdown(f"**ระยะทาง:** {float(p['distance_km']):.2f} กม.")
                except Exception:
                    pass

            if desc:
                st.markdown(f'<div class="place-desc">{desc}</div>', unsafe_allow_html=True)
            else:
                st.write("ยังไม่มีคำอธิบายเพิ่มเติม")

            if hi:
                st.markdown(
                    f'<div class="place-highlight"><b>จุดเด่น:</b> {hi}</div>',
                    unsafe_allow_html=True
                )

            if map_link:
                st.link_button("เปิดแผนที่", map_link, use_container_width=False)


# =========================================================
# MAIN LAYOUT
# =========================================================
left_col, right_col = st.columns([1.08, 0.92], gap="large")

with left_col:
    st.subheader("แชทกับผู้ช่วยปะทิว")

    chat_area = st.container(height=620, border=True)
    with chat_area:
        for msg in st.session_state.messages:
            render_chat_bubble(msg["role"], msg["content"])

with right_col:
    st.subheader("ผลลัพธ์ล่าสุด")

    result_area = st.container(height=620, border=True)
    with result_area:
        last_results = st.session_state.get("last_results", [])
        if last_results:
            for p in last_results:
                _render_place_card(p)
        else:
            st.markdown("""
            <div class="empty-box">
                ยังไม่มีผลลัพธ์ล่าสุด<br><br>
                ลองถามเช่น<br>
                <b>มีร้านอาหารแนะนำไหม</b><br>
                <b>ขอคาเฟ่ในปะทิว</b><br>
                <b>ขอแผนที่ของสถานที่นี้</b>
            </div>
            """, unsafe_allow_html=True)


# =========================================================
# CHAT INPUT
# =========================================================
user_input = st.chat_input("พิมพ์ชื่อสถานที่ ประเภทสถานที่ หรือตำบลที่ต้องการได้เลย...")


# =========================================================
# PROCESS
# =========================================================
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    result = get_answer(
        user_input,
        user_lat=None,
        user_lng=None,
        history=st.session_state.messages[-8:],
        focus_place_id=st.session_state.get("focus_place_id"),
        last_results=st.session_state.get("last_results", []),
        banned_categories=st.session_state.get("banned_categories", []),
    )

    if isinstance(result, tuple) and len(result) == 3:
        reply_text, places, banned_out = result
        st.session_state["banned_categories"] = (
            banned_out or st.session_state.get("banned_categories", [])
        )
    else:
        reply_text, places = result

    st.session_state.messages.append({"role": "assistant", "content": reply_text})

    if places:
        st.session_state["last_results"] = places
        if len(places) == 1 and places[0].get("id") is not None:
            st.session_state["focus_place_id"] = places[0]["id"]

    safe_rerun()


# =========================================================
# FOOTER
# =========================================================
st.caption("Pathew Chatbot")