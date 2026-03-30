import json
import re
from urllib.parse import quote, urlparse, parse_qs

import streamlit as st
from chatbot import get_answer
from config import MAPS_API_KEY

try:
    from streamlit_javascript import st_javascript
except Exception:
    st_javascript = None


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Pathew Chatbot",
    page_icon="📍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# LIGHT CSS ONLY (ไม่แต่งแรงเกิน)
# =========================================================
st.markdown("""
<style>
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

.result-card {
    border: 1px solid rgba(128,128,128,0.25);
    border-radius: 16px;
    padding: 12px;
    margin-bottom: 12px;
}

.result-title {
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 0.25rem;
}

.result-meta {
    font-size: 0.9rem;
    opacity: 0.9;
    margin-bottom: 0.4rem;
}

.result-highlight {
    border-left: 4px solid #3b82f6;
    padding-left: 10px;
    margin-top: 8px;
    margin-bottom: 8px;
}

.empty-box {
    border: 1px dashed rgba(128,128,128,0.35);
    border-radius: 14px;
    padding: 18px;
    text-align: center;
    opacity: 0.9;
}
</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER
# =========================================================
st.markdown("""
<div class="hero-box">
    <h2 style="margin:0 0 6px 0;">📍 AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</h2>
    <div class="small-note">
        ค้นหาร้านอาหาร คาเฟ่ ที่พัก สถานที่ท่องเที่ยว ปั๊มน้ำมัน ร้านขายยา และสถานที่ใกล้คุณในอำเภอปะทิว
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


def send_user_message(text: str):
    st.session_state["pending_input"] = text
    safe_rerun()


# =========================================================
# SESSION STATE
# =========================================================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "สวัสดีครับ 👋 อยากหาสถานที่แบบไหนในอำเภอปะทิว บอกผมได้เลยครับ"
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

if "pending_input" not in st.session_state:
    st.session_state.pending_input = None


# =========================================================
# GEOLOCATION
# =========================================================
user_lat = st.session_state.get("user_lat")
user_lng = st.session_state.get("user_lng")

if st_javascript and (user_lat is None or user_lng is None):
    try:
        coords = st_javascript("navigator.geolocation.getCurrentPosition((p) => p.coords);")
        if isinstance(coords, dict):
            lat = coords.get("latitude")
            lng = coords.get("longitude")
            if lat is not None and lng is not None:
                st.session_state["user_lat"] = float(lat)
                st.session_state["user_lng"] = float(lng)
                user_lat, user_lng = float(lat), float(lng)
    except Exception:
        pass


# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.subheader("แผงควบคุม")

    st.markdown("**สถานะระบบ**")
    if st.session_state.user_lat is not None and st.session_state.user_lng is not None:
        st.success("รับตำแหน่งปัจจุบันแล้ว")
    else:
        st.warning("ยังไม่ได้รับตำแหน่งปัจจุบัน")

    st.markdown("---")

    st.markdown("**ตัวอย่างคำถาม**")
    st.caption(
        "- มีร้านอาหารแถวนี้ไหม\n"
        "- ขอคาเฟ่ในปะทิว\n"
        "- มีปั๊มน้ำมันใกล้ฉันไหม\n"
        "- ตลาดเลริวเซ็นอยู่ห่างจากผมกี่กิโล"
    )

    st.markdown("**ปุ่มลัดเริ่มค้นหา**")
    if st.button("ร้านอาหาร", use_container_width=True):
        send_user_message("มีร้านอาหารแนะนำไหม")
    if st.button("คาเฟ่", use_container_width=True):
        send_user_message("มีคาเฟ่แนะนำไหม")
    if st.button("ที่เที่ยว", use_container_width=True):
        send_user_message("มีสถานที่ท่องเที่ยวแนะนำไหม")
    if st.button("ที่พัก", use_container_width=True):
        send_user_message("มีที่พักแนะนำไหม")
    if st.button("มีปั๊มน้ำมัน", use_container_width=True):
        send_user_message("มีปั๊มน้ำมันใกล้ฉันไหม")
    if st.button("ร้านขายยา / คลินิก", use_container_width=True):
        send_user_message("มีร้านขายยาหรือคลินิกแถวนี้ไหม")

    st.markdown("---")

    if st.button("ล้างผลลัพธ์ล่าสุด", use_container_width=True):
        st.session_state["last_results"] = []
        st.session_state["focus_place_id"] = None
        safe_rerun()

    if st.button("เริ่มแชทใหม่", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "สวัสดีครับ 👋 อยากหาสถานที่แบบไหนในอำเภอปะทิว บอกผมได้เลยครับ"
            }
        ]
        st.session_state["last_results"] = []
        st.session_state["focus_place_id"] = None
        st.session_state["banned_categories"] = []
        safe_rerun()


# =========================================================
# RENDER PLACE CARD
# =========================================================
def _render_place_card(p: dict):
    name = p.get("name", "-")
    desc = (p.get("description") or "").strip()
    hi = (p.get("highlight") or "").strip()
    tambon = p.get("tambon", "-")
    category = p.get("category", "-")
    lat = p.get("latitude")
    lng = p.get("longitude")
    place_id = p.get("id")

    map_link = None
    if lat is not None and lng is not None:
        map_link = f"https://www.google.com/maps?q={lat},{lng}"

    with st.container(border=True):
        col1, col2 = st.columns([1, 1.4], gap="medium")

        with col1:
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

        with col2:
            st.markdown(f"### {name}")
            st.caption(f"ประเภท: {category} | ตำบล: {tambon}")

            if "distance_km" in p and p.get("distance_km") is not None:
                try:
                    st.markdown(f"**ระยะทางจากคุณ:** {float(p['distance_km']):.2f} กม.")
                except Exception:
                    pass

            if desc:
                st.write(desc)
            else:
                st.write("ยังไม่มีคำอธิบายเพิ่มเติม")

            if hi:
                st.markdown(f"**จุดเด่น:** {hi}")

            btn1, btn2 = st.columns(2)

            with btn1:
                if map_link:
                    st.link_button("เปิดแผนที่", map_link, use_container_width=True)

            with btn2:
                if place_id is not None and st.button("คุยต่อเกี่ยวกับที่นี่", key=f"focus_{place_id}", use_container_width=True):
                    st.session_state["focus_place_id"] = place_id
                    safe_rerun()


# =========================================================
# MAIN LAYOUT
# =========================================================
left_col, right_col = st.columns([1.1, 0.9], gap="large")

with left_col:
    st.subheader("แชทกับผู้ช่วย")

    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("ร้านอาหาร", use_container_width=True):
            send_user_message("มีร้านอาหารแนะนำไหม")
    with q2:
        if st.button("คาเฟ่", use_container_width=True):
            send_user_message("มีคาเฟ่แนะนำไหม")
    with q3:
        if st.button("ใกล้ฉัน", use_container_width=True):
            send_user_message("มีสถานที่ใกล้ฉันไหม")
    with q4:
        if st.button("ที่เที่ยว", use_container_width=True):
            send_user_message("มีที่เที่ยวแนะนำไหม")

    chat_area = st.container(height=620, border=True)
    with chat_area:
        for msg in st.session_state.messages:
            avatar = avatar_user if msg["role"] == "user" else avatar_bot
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])

with right_col:
    st.subheader("ผลลัพธ์ล่าสุด")

    if st.session_state.get("focus_place_id"):
        st.info("ตอนนี้ระบบกำลังโฟกัสสถานที่ที่คุณเลือกไว้ คุณสามารถถามต่อได้ เช่น 'ที่นี่เด่นอะไร' หรือ 'มีอะไรใกล้ที่นี่บ้าง'")

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
                หรือ<br>
                <b>หิว มีอะไรกินแถวนี้บ้าง</b>
            </div>
            """, unsafe_allow_html=True)


# =========================================================
# CHAT INPUT
# =========================================================
user_input = st.chat_input("พิมพ์ชื่อสถานที่ ประเภทสถานที่ หรือถามแบบทั่วไปได้เลย...")


# =========================================================
# HANDLE QUICK BUTTON INPUT
# =========================================================
if not user_input and st.session_state.get("pending_input"):
    user_input = st.session_state["pending_input"]
    st.session_state["pending_input"] = None


# =========================================================
# PROCESS
# =========================================================
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})

    result = get_answer(
        user_input,
        user_lat=st.session_state.get("user_lat"),
        user_lng=st.session_state.get("user_lng"),
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
st.caption("Pathew Chatbot • ระบบแนะนำสถานที่ในอำเภอปะทิว")