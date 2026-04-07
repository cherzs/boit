"""
app.py — ZeusX Auto Re-Lister Dashboard
==========================================
Streamlit UI for managing the ZeusX auto re-listing bot.

Features:
- Session management (login / logout)
- Seller profile scanning
- Product list with enable/disable toggles
- Start/Stop bot controls
- Real-time activity log
"""

import os
import threading
import time
import streamlit as st
from datetime import datetime

import engine

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="ZeusX Auto Re-Lister",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Premium dark theme styling
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Status cards */
.card {
    background: linear-gradient(135deg, #1e1e2f 0%, #2d2d44 100%);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.8rem;
}
.card h4 {
    margin: 0 0 4px 0;
    color: #8888aa;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.card .val {
    font-size: 1.6rem;
    font-weight: 700;
}

/* Log console */
.log-box {
    background: #0a0a14;
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 1rem;
    max-height: 420px;
    overflow-y: auto;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem;
    line-height: 1.7;
}
.log-box .ln { color: #b0b0d0; padding: 1px 0; }
.log-box .ts { color: #6366f1; font-weight: 600; }

/* Product table */
.product-row {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    margin-bottom: 0.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.product-title { font-weight: 600; color: #e0e0ff; }
.product-price { color: #22c55e; font-weight: 700; font-size: 1.05rem; }
.product-date { color: #888; font-size: 0.8rem; }

/* Section dividers */
.sec {
    font-size: 1.05rem;
    font-weight: 700;
    color: #d0d0f0;
    margin: 1.5rem 0 0.7rem 0;
    padding-bottom: 0.35rem;
    border-bottom: 2px solid rgba(99,102,241,0.25);
}

/* Button upgrade */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(99,102,241,0.25);
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "logs": [],
        "running": False,
        "stop_event": threading.Event(),
        "worker_thread": None,
        "cycle_count": 0,
        "last_success": "—",
        "scanning": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()


def add_log(msg: str):
    """Thread-safe log appender."""
    st.session_state.logs.append(msg)
    if len(st.session_state.logs) > 500:
        st.session_state.logs = st.session_state.logs[-500:]
    if "── Cycle" in msg:
        st.session_state.cycle_count += 1
    if "✅" in msg and "created" in msg.lower():
        st.session_state.last_success = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Load persistent data
cfg = engine.load_config()
products = engine.load_products()


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔐 Session")

    if engine.has_session():
        st.success("✅ Session active")
    else:
        st.warning("⚠️ No session — login first")

    st.markdown("### Login Options:")
    
    # Option 1: Auto-fill login
    if st.button("🚀 Start with Auto-Fill", use_container_width=True, type="primary"):
        # Trigger bot start which will open browser with auto-fill
        st.info("Click '▶️ Start Bot' button in main panel")
    
    # Option 2: Import from Chrome
    st.markdown("<div style='margin:5px 0;'></div>", unsafe_allow_html=True)
    if st.button("📥 Import from Chrome/Edge", use_container_width=True):
        with st.spinner("Importing session from browser…"):
            success = engine.import_session_from_chrome(log_cb=add_log)
        if success:
            st.success("✅ Session imported!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("❌ Failed to import. Make sure you are logged in to ZeusX in Chrome/Edge.")
    
    # Option 3: Manual login
    st.markdown("<div style='margin:5px 0;'></div>", unsafe_allow_html=True)
    if st.button("🌐 Open ZeusX Login", use_container_width=True):
        with st.spinner("Opening browser…"):
            engine.open_login_browser(log_cb=add_log)
        st.rerun()
    
    # Logout button
    if engine.has_session():
        st.markdown("<div style='margin:5px 0;'></div>", unsafe_allow_html=True)
        if st.button("🗑️ Logout / Clear Session", use_container_width=True):
            os.remove(engine.AUTH_FILE)
            st.rerun()
    
    # Info box
    st.markdown("""
    <div style="background-color:#e7f3ff; color:#0066cc; padding:10px; border-radius:5px; font-size:0.8rem; margin-top:15px; border-left:3px solid #0066cc;">
    <b>💡 Tips:</b><br>
    • <b>Auto-Fill:</b> Isi config.json lalu Start Bot<br>
    • <b>Import:</b> Login di Chrome dulu, lalu klik Import<br>
    • <b>Manual:</b> Buka ZeusX login di browser biasa
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("## ⚙️ Settings")

    seller_url = st.text_input(
        "Seller Profile URL",
        value=cfg.get("seller_url", ""),
        placeholder="https://zeusx.com/seller/yourstore-123456",
    )
    interval = st.number_input(
        "Interval (minutes)",
        min_value=1, max_value=1440,
        value=cfg.get("interval_minutes", 10),
        step=1,
    )
    # Auto-save config
    engine.save_config({
        "seller_url": seller_url,
        "interval_minutes": interval,
        "headless": False,  # Always show browser window
    })


# ═══════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("# 🚀 ZeusX Auto Re-Lister")
st.caption("Keep your products at the top — automatically re-list on schedule")


# ═══════════════════════════════════════════════════════════════════════════
# STATUS CARDS
# ═══════════════════════════════════════════════════════════════════════════
c1, c2, c3, c4 = st.columns(4)

with c1:
    color = "#22c55e" if st.session_state.running else "#ef4444"
    label = "RUNNING" if st.session_state.running else "STOPPED"
    st.markdown(f'<div class="card"><h4>Bot Status</h4><div class="val" style="color:{color}">● {label}</div></div>', unsafe_allow_html=True)

with c2:
    st.markdown(f'<div class="card"><h4>Products</h4><div class="val" style="color:#6366f1">{len(products)}</div></div>', unsafe_allow_html=True)

with c3:
    st.markdown(f'<div class="card"><h4>Cycles Done</h4><div class="val" style="color:#a78bfa">{st.session_state.cycle_count}</div></div>', unsafe_allow_html=True)

with c4:
    st.markdown(f'<div class="card"><h4>Last Success</h4><div class="val" style="color:#f59e0b;font-size:0.95rem">{st.session_state.last_success}</div></div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT SCANNING
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">📦 Products</div>', unsafe_allow_html=True)

scan_col, info_col = st.columns([1, 3])
with scan_col:
    if st.button("🔍 Scan My Products", use_container_width=True, disabled=st.session_state.running):
        if not engine.has_session():
            st.error("Please login first!")
        elif not seller_url.strip():
            st.error("Enter your Seller Profile URL in the sidebar!")
        else:
            with st.spinner("Scanning your products on ZeusX…"):
                scanned = engine.scan_all_products(
                    seller_url=seller_url,
                    headless=headless,
                    log_cb=add_log,
                )
                products = scanned
            st.rerun()

with info_col:
    if products:
        st.caption(f"Found {len(products)} product(s). Toggle which ones to auto re-list.")
    else:
        st.caption("No products scanned yet. Click **Scan My Products** to fetch your listings.")


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT LIST
# ═══════════════════════════════════════════════════════════════════════════
if products:
    updated = False

    for i, p in enumerate(products):
        with st.container():
            # Check if in edit mode
            edit_key = f"edit_mode_{i}"
            if edit_key not in st.session_state:
                st.session_state[edit_key] = False
            
            is_editing = st.session_state[edit_key]
            
            if is_editing:
                # Edit mode - show input fields
                cols = st.columns([0.5, 4, 1.5, 2, 1])
                
                with cols[0]:
                    enabled = st.checkbox(
                        "Enable",
                        value=p.get("enabled", True),
                        key=f"enable_edit_{i}",
                        label_visibility="collapsed",
                        disabled=True,
                    )
                
                with cols[1]:
                    new_title = st.text_input(
                        "Product Name",
                        value=p.get("title", ""),
                        key=f"title_input_{i}",
                        label_visibility="collapsed",
                    )
                
                with cols[2]:
                    new_price = st.text_input(
                        "Price",
                        value=str(p.get("price", "")),
                        key=f"price_input_{i}",
                        label_visibility="collapsed",
                    )
                
                with cols[3]:
                    st.caption("Editing...")
                
                with cols[4]:
                    save_col, cancel_col = st.columns(2)
                    with save_col:
                        if st.button("✅", key=f"save_{i}", help="Save changes"):
                            products[i]["title"] = new_title
                            try:
                                products[i]["price"] = float(new_price)
                            except:
                                pass
                            st.session_state[edit_key] = False
                            updated = True
                    with cancel_col:
                        if st.button("❌", key=f"cancel_{i}", help="Cancel"):
                            st.session_state[edit_key] = False
                            st.rerun()
            
            else:
                # Normal mode - show product info
                cols = st.columns([0.5, 4, 1.5, 2, 1.5])

                with cols[0]:
                    enabled = st.checkbox(
                        "Enable",
                        value=p.get("enabled", True),
                        key=f"enable_{i}",
                        label_visibility="collapsed",
                    )
                    if enabled != p.get("enabled", True):
                        products[i]["enabled"] = enabled
                        updated = True

                with cols[1]:
                    title = p.get("title", "Untitled")
                    st.markdown(f"**{title[:80]}**")

                with cols[2]:
                    price = p.get("price", "—")
                    st.markdown(f"💰 ${price}")

                with cols[3]:
                    last = p.get("last_relisted")
                    if last:
                        st.caption(f"🔄 {last[:16]}")
                    else:
                        st.caption("🔄 Never")

                with cols[4]:
                    edit_col, img_col = st.columns([1, 1])
                    with edit_col:
                        if st.button("✏️", key=f"edit_{i}", help="Edit product"):
                            st.session_state[edit_key] = True
                            st.rerun()
                    with img_col:
                        n_imgs = len(p.get("local_images", []))
                        st.caption(f"🖼️ {n_imgs}")

    if updated:
        engine.save_products(products)
        st.rerun()

    # Summary
    enabled_count = sum(1 for p in products if p.get("enabled", True))
    st.info(f"**{enabled_count}** of {len(products)} product(s) enabled for re-listing")
else:
    st.markdown(
        '<div style="text-align:center; padding:2rem; color:#666">'
        '📭 No products loaded. Scan your seller profile to get started.'
        '</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CONTROLS
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">🎮 Controls</div>', unsafe_allow_html=True)

btn1, btn2, _ = st.columns([1, 1, 3])

with btn1:
    if not st.session_state.running:
        st.info("ℹ️ Bot will open a browser window to re-list products")
        if st.button("▶️ Start Bot", type="primary", use_container_width=True):
            enabled_products = [p for p in products if p.get("enabled", True)]
            if not engine.has_session():
                st.error("Please login first!")
            elif not enabled_products:
                st.error("No products enabled! Scan products first.")
            else:
                st.session_state.running = True
                st.session_state.stop_event.clear()

                t = threading.Thread(
                    target=engine.run_loop,
                    kwargs={
                        "interval_minutes": interval,
                        "log_cb": add_log,
                        "stop_event": st.session_state.stop_event,
                    },
                    daemon=True,
                )
                t.start()
                st.session_state.worker_thread = t
                add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🟢 Bot started - Browser will open")
                st.rerun()

with btn2:
    if st.session_state.running:
        if st.button("⏹️ Stop Bot", type="secondary", use_container_width=True):
            st.session_state.stop_event.set()
            st.session_state.running = False
            add_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🔴 Bot stopped")
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# LOG CONSOLE
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<div class="sec">📋 Activity Log</div>', unsafe_allow_html=True)

if st.session_state.logs:
    lines_html = ""
    for line in reversed(st.session_state.logs[-100:]):
        if line.startswith("["):
            bracket = line.find("]") + 1
            lines_html += f'<div class="ln"><span class="ts">{line[:bracket]}</span>{line[bracket:]}</div>'
        else:
            lines_html += f'<div class="ln">{line}</div>'

    st.markdown(f'<div class="log-box">{lines_html}</div>', unsafe_allow_html=True)

    if st.button("🧹 Clear Logs"):
        st.session_state.logs = []
        st.rerun()
else:
    st.markdown(
        '<div class="log-box">'
        '<div class="ln" style="color:#555">No activity yet. Scan products or start the bot.</div>'
        '</div>',
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH (while bot is running, poll every 5s)
# ═══════════════════════════════════════════════════════════════════════════
if st.session_state.running:
    import time as _t
    _t.sleep(5)
    st.rerun()
