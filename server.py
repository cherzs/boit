"""
server.py — ZeusX Auto Re-Lister Web Server
=============================================
Flask backend with SocketIO for real-time log streaming.

API:
  GET  /api/status          → bot status, products, settings, logs
  POST /api/login           → open browser for manual login
  POST /api/scan            → scan seller products
  POST /api/start           → start bot loop
  POST /api/stop            → stop bot loop
  POST /api/settings        → update interval / seller URL / headless
  POST /api/product/toggle  → enable/disable a product
"""

import threading
from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO
from datetime import datetime

import engine

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = "zeusx-auto-relister-secret"
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
bot_state = {
    "running": False,
    "stop_event": threading.Event(),
    "worker_thread": None,
    "logs": [],
    "cycle_count": 0,
    "last_success": None,
}


def log_callback(message: str):
    """Push log to state and emit via SocketIO."""
    bot_state["logs"].append(message)
    if len(bot_state["logs"]) > 500:
        bot_state["logs"] = bot_state["logs"][-500:]

    # Track metrics
    if "Cycle" in message:
        bot_state["cycle_count"] += 1
    if "created successfully" in message.lower():
        bot_state["last_success"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    socketio.emit("log", {"message": message})
    socketio.emit("status_update", _build_status())


def _build_status() -> dict:
    products = engine.load_products()
    cfg = engine.load_config()
    enabled_count = sum(1 for p in products if p.get("enabled", True))
    return {
        "running": bot_state["running"],
        "has_session": engine.has_session(),
        "product_count": len(products),
        "enabled_count": enabled_count,
        "cycle_count": bot_state["cycle_count"],
        "last_success": bot_state["last_success"],
        "settings": cfg,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(_build_status())


@app.route("/api/products")
def api_products():
    products = engine.load_products()
    # Don't send full image paths to frontend
    safe = []
    for p in products:
        # Only count actual product images (cdn-offer-photos), not avatars/tracking
        offer_images = [img for img in p.get("images", []) if "cdn-offer-photos" in img]
        safe.append({
            "url": p.get("url", ""),
            "title": p.get("title", "Untitled"),
            "price": p.get("price", "-"),
            "description": (p.get("description", "") or "")[:150],
            "enabled": p.get("enabled", True),
            "last_relisted": p.get("last_relisted"),
            "image_count": len(offer_images),
        })
    return jsonify(safe)

@app.route("/api/product/detail")
def api_product_detail():
    url = request.args.get("url", "")
    products = engine.load_products()
    for p in products:
        if p.get("url") == url:
            offer_images = [img for img in p.get("images", []) if "cdn-offer-photos" in img]
            return jsonify({
                "url": p.get("url", ""),
                "title": p.get("title", "Untitled"),
                "price": p.get("price", "-"),
                "description": p.get("description", ""),
                "images": offer_images,
                "all_images": p.get("images", []),
                "local_images": len(p.get("local_images", [])),
                "enabled": p.get("enabled", True),
                "last_relisted": p.get("last_relisted"),
                "scraped_at": p.get("scraped_at", ""),
                "quantity": p.get("quantity", "-"),
                "game_name": p.get("game_name", "-"),
                "sub_game": p.get("sub_game", "-"),
                "delivery_time": p.get("delivery_time", "-"),
                "delivery_method": p.get("delivery_method", "-"),
            })
    return jsonify({"error": "Product not found"}), 404


@app.route("/api/logs")
def api_logs():
    return jsonify(bot_state["logs"][-100:])


@app.route("/api/login", methods=["POST"])
def api_login():
    if bot_state["running"]:
        return jsonify({"error": "Stop the bot first"}), 400

    def do_login():
        engine.open_login_browser(log_cb=log_callback)
        socketio.emit("status_update", _build_status())

    t = threading.Thread(target=do_login, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Browser opening — log in then close it"})


@app.route("/api/import", methods=["POST"])
def api_import():
    if bot_state["running"]:
        return jsonify({"error": "Stop the bot first"}), 400
    
    def do_import():
        success = engine.import_session_from_chrome(log_cb=log_callback)
        socketio.emit("status_update", _build_status())
        return success
    
    # Run in thread to not block
    success = do_import()
    return jsonify({"ok": True, "success": success, "message": "Import completed"})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if bot_state["running"]:
        return jsonify({"error": "Stop the bot first"}), 400
    if not engine.has_session():
        return jsonify({"error": "Login first"}), 400

    cfg = engine.load_config()
    data = request.json or {}
    store_url = data.get("store_url", "").strip()

    def do_scan():
        engine.scan_all_products(
            headless=cfg.get("headless", False),
            log_cb=log_callback,
            store_url=store_url,
        )
        socketio.emit("products_updated", True)
        socketio.emit("status_update", _build_status())

    t = threading.Thread(target=do_scan, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Scanning started"})


@app.route("/api/start", methods=["POST"])
def api_start():
    if bot_state["running"]:
        return jsonify({"error": "Bot already running"}), 400

    products = engine.load_products()
    enabled = [p for p in products if p.get("enabled", True)]
    if not enabled:
        return jsonify({"error": "No products enabled"}), 400
    if not engine.has_session():
        return jsonify({"error": "Login first"}), 400

    cfg = engine.load_config()
    bot_state["running"] = True
    bot_state["stop_event"].clear()

    def on_done():
        bot_state["running"] = False
        socketio.emit("status_update", _build_status())
        # Emit event so frontend can show a notification
        socketio.emit("relist_complete", True)

    def run_wrapper():
        try:
            engine.run_once(
                headless=cfg.get("headless", False),
                log_cb=log_callback,
                stop_event=bot_state["stop_event"],
            )
        finally:
            on_done()

    t = threading.Thread(target=run_wrapper, daemon=True)
    t.start()
    bot_state["worker_thread"] = t

    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] Bot started manual run")
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if not bot_state["running"]:
        return jsonify({"error": "Bot not running"}), 400

    bot_state["stop_event"].set()
    bot_state["running"] = False
    log_callback(f"[{datetime.now().strftime('%H:%M:%S')}] Bot stopped")
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True})


@app.route("/api/settings", methods=["POST"])
def api_settings():
    data = request.json or {}
    cfg = engine.load_config()
    if "headless" in data:
        cfg["headless"] = bool(data["headless"])
    engine.save_config(cfg)
    return jsonify({"ok": True, "settings": cfg})


@app.route("/api/product/toggle", methods=["POST"])
def api_toggle_product():
    data = request.json or {}
    url = data.get("url", "")
    products = engine.load_products()
    for p in products:
        if p.get("url") == url:
            p["enabled"] = not p.get("enabled", True)
            engine.save_products(products)
            return jsonify({"ok": True, "enabled": p["enabled"]})
    return jsonify({"error": "Product not found"}), 404


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    bot_state["logs"] = []
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("ZeusX Auto Re-Lister running at http://localhost:8000")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)
