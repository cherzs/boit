"""
server.py — ZeusX Auto Listing Web Server
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

import base64
import os
import re
import threading
from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_socketio import SocketIO
from datetime import datetime

import engine
import database as db

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


def _save_uploaded_images(image_items) -> list:
    """Save base64 image payloads from the dashboard and return local paths."""
    import uuid

    saved_images = []
    if not isinstance(image_items, list):
        return saved_images

    os.makedirs(engine.IMAGES_DIR, exist_ok=True)
    for item in image_items[:8]:
        if not isinstance(item, dict):
            continue
        raw = item.get("data") or ""
        match = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", raw, re.IGNORECASE)
        if not match:
            continue
        ext = "jpg" if match.group(1).lower() in ("jpg", "jpeg") else match.group(1).lower()
        try:
            image_bytes = base64.b64decode(match.group(2), validate=True)
        except Exception:
            continue
        if not image_bytes:
            continue
        filename = f"manual_{uuid.uuid4().hex[:16]}.{ext}"
        path = os.path.join(engine.IMAGES_DIR, filename)
        with open(path, "wb") as f:
            f.write(image_bytes)
        saved_images.append(path)
    return saved_images


def _build_status() -> dict:
    products = engine.load_products()
    cfg = engine.load_config()
    enabled_count = sum(1 for p in products if p.get("enabled", True))
    duplicate_titles = engine.get_duplicate_titles(products)
    
    return {
        "running": bot_state["running"],
        "has_session": engine.has_session(),
        "product_count": len(products),
        "enabled_count": enabled_count,
        "duplicate_titles": duplicate_titles,
        "cycle_count": bot_state["cycle_count"],
        "last_success": bot_state["last_success"],
        "settings": {
            "headless": cfg.get("headless", False),
            "seller_url": cfg.get("seller_url", ""),
            "interval_minutes": cfg.get("interval_minutes", 10),
            "use_manual_browser": cfg.get("use_manual_browser", False),
        },
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
    safe = []
    for p in products:
        # Only count actual product images (cdn-offer-photos), not avatars/tracking
        offer_images = [img for img in p.get("images", []) if "cdn-offer-photos" in img]
        local_images = p.get("local_images", []) or []
        safe.append({
            "url": p.get("url", ""),
            "title": p.get("title", "Untitled"),
            "price": p.get("price", "-"),
            "description": (p.get("description", "") or "")[:150],
            "game_name": p.get("game_name", ""),
            "item_type": p.get("item_type", "In-Game Items"),
            "sub_game": p.get("sub_game", ""),
            "enabled": p.get("enabled", True),
            "last_relisted": p.get("last_relisted"),
            "image_count": len(offer_images) + len(local_images),
            "local_images": local_images,
        })
    return jsonify(safe)

@app.route("/api/product/detail")
def api_product_detail():
    url = request.args.get("url", "")
    products = engine.load_products()
    for p in products:
        if p.get("url") == url:
            offer_images = [img for img in p.get("images", []) if "cdn-offer-photos" in img]
            local_images = p.get("local_images", []) or []
            local_image_urls = []
            for path in local_images:
                filename = os.path.basename(path)
                if filename:
                    local_image_urls.append(f"/images/{filename}")
            local_image_items = [
                {"path": path, "url": f"/images/{os.path.basename(path)}"}
                for path in local_images
                if os.path.basename(path)
            ]
            return jsonify({
                "url": p.get("url", ""),
                "title": p.get("title", "Untitled"),
                "price": p.get("price", "-"),
                "description": p.get("description", ""),
                "images": offer_images,
                "all_images": p.get("images", []),
                "local_images": len(local_images),
                "local_image_urls": local_image_urls,
                "local_image_items": local_image_items,
                "enabled": p.get("enabled", True),
                "last_relisted": p.get("last_relisted"),
                "scraped_at": p.get("scraped_at", ""),
                "quantity": p.get("quantity", "-"),
                "game_name": p.get("game_name", "-"),
                "item_type": p.get("item_type", "In-Game Items"),
                "sub_game": p.get("sub_game", "-"),
                "delivery_time": p.get("delivery_time", "-"),
                "delivery_hours": p.get("delivery_hours", 0),
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
        engine.open_login_browser_manual(log_cb=log_callback)
        socketio.emit("status_update", _build_status())

    t = threading.Thread(target=do_login, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Browser opening — log in manually then session will be saved"})


@app.route("/api/scan", methods=["POST"])
def api_scan():
    if bot_state["running"]:
        return jsonify({"error": "Stop the bot first"}), 400

    cfg = engine.load_config()
    data = request.json or {}
    
    # Gunakan store_url dari request, atau dari config, atau default
    store_url = data.get("store_url", "").strip()
    if not store_url:
        store_url = cfg.get("seller_url", "").strip()
    if not store_url:
        store_url = "https://zeusx.com/seller/gstore-657837"  # Default URL

    def do_scan():
        try:
            engine.scan_all_products(
                headless=cfg.get("headless", False),
                log_cb=log_callback,
                store_url=store_url,
            )
        except FileNotFoundError as exc:
            log_callback(f"Scan failed: Playwright is not installed correctly ({exc})")
            log_callback("Run: ./venv/bin/python -m pip install --force-reinstall playwright playwright-stealth")
            log_callback("Then run: ./venv/bin/python -m playwright install chromium")
        except Exception as exc:
            log_callback(f"Scan failed: {exc}")
        finally:
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

    def run_wrapper():
        results = []
        try:
            results = engine.run_once(
                headless=cfg.get("headless", False),
                log_cb=log_callback,
                stop_event=bot_state["stop_event"],
            ) or []
        finally:
            bot_state["running"] = False
            socketio.emit("status_update", _build_status())
            socketio.emit("relist_complete", {
                "results": results,
                "total": len(results),
                "success": sum(1 for r in results if r.get("success")),
                "failed": sum(1 for r in results if not r.get("success")),
            })

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
    if "seller_url" in data:
        cfg["seller_url"] = data["seller_url"]
    if "interval_minutes" in data:
        cfg["interval_minutes"] = int(data["interval_minutes"])
    if "use_manual_browser" in data:
        cfg["use_manual_browser"] = bool(data["use_manual_browser"])
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


@app.route("/api/product/toggle_all", methods=["POST"])
def api_toggle_all_products():
    data = request.json or {}
    enable = data.get("enable", True)
    products = engine.load_products()
    if products:
        for p in products:
            p["enabled"] = bool(enable)
        engine.save_products(products)
    return jsonify({"ok": True})


@app.route("/api/product/update", methods=["POST"])
def api_update_product():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    products = engine.load_products()
    updated = False
    for p in products:
        if p.get("url", "").strip() == url:
            if "title" in data:
                p["title"] = (data["title"] or "").strip()
            if "price" in data:
                try:
                    p["price"] = float(data["price"])
                except:
                    pass
            if "description" in data:
                p["description"] = data.get("description", "")
            if "game_name" in data:
                p["game_name"] = data.get("game_name", "")
            if "item_type" in data:
                p["item_type"] = data.get("item_type", "In-Game Items") or "In-Game Items"
            if "sub_game" in data:
                p["sub_game"] = data.get("sub_game", "")
            if "quantity" in data:
                try:
                    p["quantity"] = int(data.get("quantity") or 0)
                except Exception:
                    pass
            if "delivery_method" in data:
                p["delivery_method"] = data.get("delivery_method", "")
            if "delivery_hours" in data:
                try:
                    p["delivery_hours"] = int(data.get("delivery_hours") or 0)
                except Exception:
                    pass
            if "local_images_keep" in data:
                keep = data.get("local_images_keep") or []
                if isinstance(keep, list):
                    current = p.get("local_images", []) or []
                    keep_set = {str(path) for path in keep}
                    p["local_images"] = [path for path in current if path in keep_set]
            new_images = _save_uploaded_images(data.get("new_images") or [])
            if new_images:
                p["local_images"] = (p.get("local_images", []) or []) + new_images
            updated = True
            break
            
    if updated:
        engine.save_products(products)
        socketio.emit("products_updated", True)
        socketio.emit("status_update", _build_status())
        return jsonify({"ok": True})
        
    return jsonify({"error": "Product not found"}), 404

@app.route("/api/product/delete_bulk", methods=["POST"])
def api_delete_bulk():
    data = request.json or {}
    urls = data.get("urls", [])
    if not isinstance(urls, list) or not urls:
        return jsonify({"error": "List of URLs is required"}), 400
        
    urls_set = set(u.strip() for u in urls if u)
    products = engine.load_products()
    
    original_count = len(products)
    new_products = [p for p in products if p.get("url", "").strip() not in urls_set]
    
    engine.save_products(new_products)
    return jsonify({"ok": True, "deleted_count": original_count - len(new_products)})


@app.route("/api/product/clean_duplicates", methods=["POST"])
def api_clean_duplicates():
    removed_count = engine.remove_duplicate_products()
    socketio.emit("products_updated", True)
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True, "removed_count": removed_count})


@app.route("/api/product/delete", methods=["POST"])
def api_delete_product():
    data = request.json or {}
    url = data.get("url", "")
    products = engine.load_products()
    
    # Filter out the product with matching URL
    new_products = [p for p in products if p.get("url") != url]
    
    if len(new_products) == len(products):
        return jsonify({"error": "Product not found"}), 404
    
    engine.save_products(new_products)
    return jsonify({"ok": True, "message": "Product deleted"})


@app.route("/api/import_chrome", methods=["POST"])
def api_import_chrome():
    if bot_state["running"]:
        return jsonify({"error": "Stop the bot first"}), 400

    def do_import():
        success = engine.import_session_from_chrome(log_cb=log_callback)
        socketio.emit("status_update", _build_status())
        if success:
            log_callback("Session imported from Chrome/Edge")
        else:
            log_callback("Session import failed. Make sure you are logged in with Chrome/Edge.")

    t = threading.Thread(target=do_import, daemon=True)
    t.start()
    return jsonify({"ok": True, "message": "Importing session from Chrome/Edge..."})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    db.clear_session()
    log_callback("🗑️ Session cleared")
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True})


@app.route("/api/product/create", methods=["POST"])
def api_create_product():
    data = request.json or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400

    import uuid
    saved_images = _save_uploaded_images(data.get("images") or [])

    product = {
        "url": f"local://{uuid.uuid4().hex[:16]}",
        "title": title,
        "price": str(data.get("price", "0")),
        "description": data.get("description", ""),
        "game_name": data.get("game_name", "Roblox In Game Items"),
        "item_type": data.get("item_type", "In-Game Items") or "In-Game Items",
        "sub_game": data.get("sub_game", ""),
        "delivery_time": "",
        "delivery_hours": int(data.get("delivery_hours") or 1),
        "delivery_days": int(data.get("delivery_days") or 0),
        "delivery_method": "",
        "quantity": 20,
        "enabled": True,
        "images": [],
        "local_images": saved_images,
        "scraped_at": datetime.now().isoformat(),
        "last_relisted": None,
    }
    db.upsert_product(product)
    socketio.emit("products_updated", True)
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True, "url": product["url"], "title": product["title"]})


@app.route("/api/product/toggle_selected", methods=["POST"])
def api_toggle_selected():
    data = request.json or {}
    urls = data.get("urls", [])
    enable = data.get("enable", True)
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400
    urls_set = set(urls)
    products = engine.load_products()
    for p in products:
        if p.get("url") in urls_set:
            p["enabled"] = bool(enable)
    engine.save_products(products)
    socketio.emit("status_update", _build_status())
    return jsonify({"ok": True, "count": len(urls_set)})


@app.route("/api/migrate", methods=["POST"])
def api_migrate():
    """Migrasikan data dari file JSON lama ke SQLite."""
    result = db.migrate_from_json()
    socketio.emit("status_update", _build_status())
    return jsonify({
        "ok": len(result["errors"]) == 0,
        "migrated": result["migrated"],
        "errors": result["errors"],
        "counts": result["counts"],
    })


@app.route("/api/db_status", methods=["GET"])
def api_db_status():
    """Status database SQLite dan keberadaan file JSON lama."""
    return jsonify({
        "stats": db.db_stats(),
        "json_files": db.json_files_exist(),
    })


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    bot_state["logs"] = []
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Static files: Serve images
# ---------------------------------------------------------------------------
@app.route("/images/<path:filename>")
def serve_image(filename):
    """Serve product images from the images folder."""
    return send_from_directory(engine.IMAGES_DIR, filename)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("ZeusX Auto Listing running at http://localhost:8000")
    socketio.run(app, host="0.0.0.0", port=8000, debug=False)
