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
# CUSTOM CSS
# =========================================================
st.markdown("""
<style>
    .main {
        background: linear-gradient(180deg, #f8fbff 0%, #f4fff9 100%);
    }

    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    .hero-card {
        background: linear-gradient(135deg, #0f766e 0%, #0ea5e9 100%);
        border-radius: 22px;
        padding: 26px 28px;
        color: white;
        box-shadow: 0 10px 30px rgba(0,0,0,0.12);
        margin-bottom: 1rem;
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.2;
        margin-bottom: 0.4rem;
    }

    .hero-subtitle {
        font-size: 1rem;
        opacity: 0.95;
    }

    .section-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.65rem;
        color: #0f172a;
    }

    .small-muted {
        color: #475569;
        font-size: 0.92rem;
    }

    .info-chip-wrap {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 12px;
    }

    .info-chip {
        display: inline-block;
        padding: 7px 12px;
        border-radius: 999px;
        background: rgba(255,255,255,0.16);
        border: 1px solid rgba(255,255,255,0.18);
        font-size: 0.88rem;
    }

    .panel-card {
        background: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 20px;
        padding: 16px;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    }

    .place-card {
        background: white;
        border: 1px solid #e5e7eb;
        border-radius: 20px;
        padding: 14px;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
        margin-bottom: 14px;
    }

    .place-name {
        font-size: 1.12rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.3rem;
    }

    .meta-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 999px;
        background: #eff6ff;
        color: #1d4ed8;
        font-size: 0.8rem;
        font-weight: 600;
        margin-right: 6px;
        margin-bottom: 6px;
    }

    .meta-badge-green {
        background: #ecfdf5;
        color: #047857;
    }

    .highlight-box {
        background: #f8fafc;
        border-left: 4px solid #0ea5e9;
        padding: 10px 12px;
        border-radius: 10px;
        margin-top: 10px;
        margin-bottom: 10px;
    }

    .empty-state {
        border: 1px dashed #cbd5e1;
        background: #ffffff;
        border-radius: 18px;
        padding: 18px;
        text-align: center;
        color: #475569;
    }

    .sticky-note {
        background: #fefce8;
        border: 1px solid #fde68a;
        border-radius: 14px;
        padding: 12px 14px;
        color: #854d0e;
        font-size: 0.92rem;
    }

    .quick-guide {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        border-radius: 14px;
        padding: 12px 14px;
        color: #166534;
        font-size: 0.92rem;
    }

    div[data-testid="stChatMessage"] {
        background: rgba(255,255,255,0.72);
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 4px 8px;
        margin-bottom: 10px;
    }

    div[data-testid="stSidebar"] {
        border-right: 1px solid #e5e7eb;
    }

    .footer-note {
        margin-top: 10px;
        color: #64748b;
        font-size: 0.85rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# HEADER / HERO
# =========================================================
st.markdown("""
<div class="hero-card">
    <div class="hero-title">AI Chatbot แนะนำสถานที่ในอำเภอปะทิว</div>
    <div class="hero-subtitle">
        ค้นหาร้านอาหาร คาเฟ่ ที่พัก สถานที่ท่องเที่ยว ปั๊มน้ำมัน วัด และสถานที่ใกล้คุณในอำเภอปะทิว
    </div>
    <div class="info-chip-wrap">
        <span class="info-chip">ค้นหาจากชื่อสถานที่</span>
        <span class="info-chip">ถามแบบภาษาคนทั่วไปได้</span>
        <span class="info-chip">ดูผลลัพธ์พร้อมรูปและแผนที่</span>
        <span class="info-chip">รองรับสถานที่ใกล้ตำแหน่งปัจจุบัน</span>
    </div>
</div>
""", unsafe_allow_html=True)


# =========================================================
# AVATARS
# =========================================================
svg_user = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
<circle cx='20' cy='20' r='18' fill='#2563EB'/></svg>"""
svg_bot = """<svg xmlns='http://www.w3.org/2000/svg' width='40' height='40'>
<circle cx='20' cy='20' r='18' fill='#0F766E'/></svg>"""
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
        st.image(url, caption=caption, width="stretch")
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
            "content": "สวัสดีครับ ผมช่วยแนะนำสถานที่ในอำเภอปะทิวได้ เช่น ร้านอาหาร คาเฟ่ ที่พัก หรือสถานที่เที่ยวใกล้คุณครับ"
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
    st.markdown("แผงควบคุม")
    st.markdown(
        f"""
        <div class="panel-card">
            <div class="section-title">สถานะระบบ</div>
            <div class="small-muted">ตำแหน่งปัจจุบัน</div>
            <div style="margin-top:6px;">
                {"✅ พร้อมใช้งาน" if st.session_state.user_lat is not None and st.session_state.user_lng is not None else "⚠️ ยังไม่ได้รับตำแหน่ง"}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("")

    st.markdown(
        """
        <div class="quick-guide">
            <b>ตัวอย่างคำถาม</b><br>
            - มีร้านอาหารแถวนี้ไหม<br>
            - ขอคาเฟ่ในปะทิว<br>
            - มีปั๊มน้ำมันใกล้ฉันไหม<br>
            - ตลาดเลริวเซ็นอยู่ห่างจากผมกี่กิโล
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("### ปุ่มลัดเริ่มค้นหา")
    if st.button("ร้านอาหาร", use_container_width=True):
        send_user_message("มีร้านอาหารแนะนำไหม")
    if st.button("คาเฟ่", use_container_width=True):
        send_user_message("มีคาเฟ่แนะนำไหม")
    if st.button("ที่เที่ยว", use_container_width=True):
        send_user_message("มีสถานที่ท่องเที่ยวแนะนำไหม")
    if st.button("ที่พัก", use_container_width=True):
        send_user_message("มีที่พักแนะนำไหม")
    if st.button("ปั๊มน้ำมัน", use_container_width=True):
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
                "content": "สวัสดีครับ ผมช่วยแนะนำสถานที่ในอำเภอปะทิวได้ เช่น ร้านอาหาร คาเฟ่ ที่พัก หรือสถานที่เที่ยวใกล้คุณครับ"
            }
        ]
        st.session_state["last_results"] = []
        st.session_state["focus_place_id"] = None
        st.session_state["banned_categories"] = []
        safe_rerun()


# =========================================================
# PLACE CARD RENDERER
# =========================================================
def _render_place_card(p: dict, compact: bool = False):
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

    st.markdown('<div class="place-card">', unsafe_allow_html=True)

    img_col, info_col = st.columns([1.05, 1.45], gap="medium")

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
            st.markdown(
                """
                <div class="empty-state">
                    ไม่มีรูปภาพ<br>จะแสดงแผนที่หรือข้อมูลแทน
                </div>
                """,
                unsafe_allow_html=True
            )

    with info_col:
        st.markdown(f'<div class="place-name">{name}</div>', unsafe_allow_html=True)

        badge_html = f"""
        <span class="meta-badge">{category}</span>
        <span class="meta-badge meta-badge-green">{tambon}</span>
        """
        st.markdown(badge_html, unsafe_allow_html=True)

        if "distance_km" in p and p.get("distance_km") is not None:
            try:
                distance_text = f"{float(p['distance_km']):.2f} กม."
                st.markdown(f"**ระยะทางจากคุณ:** {distance_text}")
            except Exception:
                pass

        if desc:
            st.markdown(desc)
        else:
            st.markdown("_ยังไม่มีคำอธิบายเพิ่มเติม_")

        if hi:
            st.markdown(
                f'<div class="highlight-box"><b>จุดเด่น:</b> {hi}</div>',
                unsafe_allow_html=True
            )

        action_cols = st.columns([1, 1, 1], gap="small")

        with action_cols[0]:
            if map_link:
                st.link_button("เปิดแผนที่", map_link, use_container_width=True)

        with action_cols[1]:
            if place_id is not None and st.button("คุยต่อ", key=f"focus_{place_id}", use_container_width=True):
                st.session_state["focus_place_id"] = place_id
                safe_rerun()

        with action_cols[2]:
            if st.button("รายละเอียด", key=f"detail_{name}_{place_id}", use_container_width=True):
                st.session_state["pending_input"] = f"{name} เด่นอะไร"
                safe_rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# LAYOUT: CHAT + RESULTS
# =========================================================
left_col, right_col = st.columns([1.2, 1], gap="large")

with left_col:
    st.markdown('<div class="section-title"> แชทกับผู้ช่วย</div>', unsafe_allow_html=True)

    quick_cols = st.columns(4)
    quick_prompts = [
        ("ร้านอาหาร", "มีร้านอาหารแนะนำไหม"),
        ("คาเฟ่", "มีคาเฟ่แนะนำไหม"),
        ("ใกล้ฉัน", "มีสถานที่ใกล้ฉันไหม"),
        ("ที่เที่ยว", "มีที่เที่ยวแนะนำไหม"),
    ]
    for col, (label, prompt) in zip(quick_cols, quick_prompts):
        with col:
            if st.button(label, key=f"top_quick_{label}", use_container_width=True):
                send_user_message(prompt)

    chat_box = st.container(border=True, height=680)

    with chat_box:
        for msg in st.session_state.messages:
            avatar = avatar_user if msg["role"] == "user" else avatar_bot
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])


with right_col:
    st.markdown('<div class="section-title"> ผลลัพธ์ล่าสุด</div>', unsafe_allow_html=True)

    if st.session_state.get("focus_place_id"):
        st.markdown(
            """
            <div class="sticky-note">
                ตอนนี้ระบบกำลังโฟกัสกับสถานที่ที่คุณเลือกไว้
                คุณสามารถถามต่อได้ เช่น “ที่นี่เด่นอะไร” หรือ “มีอะไรใกล้ที่นี่บ้าง”
            </div>
            """,
            unsafe_allow_html=True
        )

    results_panel = st.container(border=True, height=680)

    with results_panel:
        last_results = st.session_state.get("last_results", [])
        if last_results:
            for p in last_results:
                _render_place_card(p, compact=True)
        else:
            st.markdown(
                """
                <div class="empty-state">
                    ยังไม่มีผลลัพธ์ล่าสุด<br><br>
                    ลองพิมพ์เช่น<br>
                    <b>“มีคาเฟ่แนะนำไหม”</b><br>
                    หรือ<br>
                    <b>“หิว มีอะไรกินแถวนี้บ้าง”</b>
                </div>
                """,
                unsafe_allow_html=True
            )


# =========================================================
# CHAT INPUT
# =========================================================
user_input = st.chat_input("พิมพ์ชื่อสถานที่ ประเภทสถานที่ หรือถามแบบทั่วไปได้เลย...")


# =========================================================
# HANDLE PENDING INPUT FROM BUTTONS
# =========================================================
if not user_input and st.session_state.get("pending_input"):
    user_input = st.session_state["pending_input"]
    st.session_state["pending_input"] = None


# =========================================================
# PROCESS MESSAGE
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
        banned_out = st.session_state.get("banned_categories", [])

    st.session_state.messages.append({"role": "assistant", "content": reply_text})

    if places:
        st.session_state["last_results"] = places
        if len(places) == 1 and places[0].get("id") is not None:
            st.session_state["focus_place_id"] = places[0]["id"]

    safe_rerun()


# =========================================================
# FOOTER
# =========================================================
st.markdown(
    '<div class="footer-note">Pathew Chatbot • ระบบแนะนำสถานที่ในอำเภอปะทิว</div>',
    unsafe_allow_html=True
)