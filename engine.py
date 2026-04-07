"""
engine.py — ZeusX Auto Re-Listing Engine
==========================================
Core automation for the re-listing bot:
1. Session management (manual login → save cookies)
2. Product scraping (seller profile → product details)
3. Re-listing loop (delete old → create new → product stays on top)

Uses Playwright + playwright_stealth for anti-detection.
"""

import json
import os
import re
import time
import random
import hashlib
import threading
import webbrowser
import requests
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Stealth import (optional graceful degradation)
try:
    from playwright_stealth import stealth_sync
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False

# ---------------------------------------------------------------------------
# Paths & Constants
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUTH_FILE = os.path.join(BASE_DIR, "auth.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
IMAGES_DIR = os.path.join(BASE_DIR, "images")
BASE_URL = "https://www.zeusx.com"

os.makedirs(IMAGES_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _log(callback, message: str):
    """Send a timestamped log line via the callback and to stdout."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {message}"
    if callback:
        callback(line)
    print(line)


def _random_delay(lo: float = 0.5, hi: float = 2.0):
    """Human-like random pause."""
    time.sleep(random.uniform(lo, hi))


def _typing_delay() -> int:
    """Per-keystroke delay in ms for page.type()."""
    return random.randint(50, 150)


def _interruptible_sleep(seconds: int, stop_event: threading.Event):
    """Sleep that can be interrupted by the stop event."""
    for _ in range(seconds):
        if stop_event.is_set():
            return
        time.sleep(1)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG & PRODUCT DATA
# ═══════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"interval_minutes": 10, "headless": False}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


def load_products() -> list:
    """Load saved product data from products.json."""
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r") as f:
            return json.load(f)
    return []


def save_products(products: list):
    """Persist product data to products.json."""
    with open(PRODUCTS_FILE, "w") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def has_session() -> bool:
    return os.path.exists(AUTH_FILE)


def save_session(context):
    context.storage_state(path=AUTH_FILE)


def open_login_browser(log_cb=None):
    """
    Open ZeusX in a Playwright browser for login.
    User can login manually, then session will be saved to auth.json
    """
    _log(log_cb, "Opening ZeusX browser for login...")
    
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        w = random.randint(1280, 1920)
        h = random.randint(800, 1080)
        context = browser.new_context(viewport={"width": w, "height": h})
        page = context.new_page()
        if HAS_STEALTH:
            stealth_sync(page)
        
        try:
            page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30_000)
            _log(log_cb, "Browser opened. Please login manually in the browser window.")
            _log(log_cb, "Browser will auto-detect successful login and save session...")
            
            # Wait for login to complete (check for redirect to dashboard or my-listing)
            logged_in = False
            max_wait = 300  # Wait up to 5 minutes
            for i in range(max_wait):
                time.sleep(1)
                current_url = page.url
                
                # Check if already logged in (redirected to dashboard or my-listing)
                if "/my-listing" in current_url or "/dashboard" in current_url:
                    logged_in = True
                    break
                
                # Also check for user menu/profile indicator
                try:
                    user_menu = page.query_selector('[class*="user-menu"], [class*="profile"], [class*="avatar"], [class*="dropdown-toggle"]')
                    if user_menu:
                        logged_in = True
                        break
                except:
                    pass
                
                if i % 10 == 0:  # Log every 10 seconds
                    _log(log_cb, f"Waiting for login... ({i}s)")
            
            if logged_in:
                save_session(context)
                _log(log_cb, "✅ Login successful! Session saved to auth.json")
            else:
                _log(log_cb, "⚠️ Login timeout. Please try again.")
                
        except Exception as e:
            _log(log_cb, f"Error during login: {e}")
        finally:
            browser.close()


def _new_context(pw, headless: bool = False):
    """Create a stealth browser context, re-using auth.json if available."""
    browser = pw.chromium.launch(headless=headless)
    w = random.randint(1280, 1920)
    h = random.randint(800, 1080)
    kwargs = {"viewport": {"width": w, "height": h}}
    if has_session():
        kwargs["storage_state"] = AUTH_FILE
    context = browser.new_context(**kwargs)
    page = context.new_page()
    if HAS_STEALTH:
        stealth_sync(page)
    return browser, context, page


# ═══════════════════════════════════════════════════════════════════════════
# CAPTCHA DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _detect_captcha(page) -> bool:
    for sel in [
        'iframe[src*="captcha"]', 'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]', '#captcha', '.g-recaptcha',
        '.h-captcha', '[class*="captcha" i]',
    ]:
        try:
            if page.query_selector(sel):
                return True
        except Exception:
            continue
    return False


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT SCRAPING
# ═══════════════════════════════════════════════════════════════════════════

def scrape_my_listings(page, log_cb=None) -> list:
    """
    Navigate to /my-listing (logged-in dashboard) and collect all product links.
    Returns a list of dicts: [{url, title}, ...]
    """
    my_listing_url = f"{BASE_URL}/my-listing"
    _log(log_cb, f"Scanning My Listing page: {my_listing_url}")

    try:
        page.goto(my_listing_url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, "WARNING: My Listing page timed out")
        return []

    _random_delay(2, 4)

    # Scroll down to load all products (lazy loading / pagination)
    prev_count = 0
    for _ in range(20):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _random_delay(1, 2)
        links = page.query_selector_all("a[href]")
        if len(links) == prev_count:
            break
        prev_count = len(links)

    return _collect_product_links(page, log_cb)


def scrape_store_page(page, store_url: str, log_cb=None) -> list:
    """
    Navigate to a public seller/store page and collect all product links.
    Returns a list of dicts: [{url, title}, ...]
    """
    _log(log_cb, f"Scanning store page: {store_url}")

    try:
        page.goto(store_url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, "WARNING: Store page timed out")
        return []

    _random_delay(2, 4)

    # Scroll down to load all products
    prev_count = 0
    for _ in range(20):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _random_delay(1, 2)
        links = page.query_selector_all("a[href]")
        if len(links) == prev_count:
            break
        prev_count = len(links)

    return _collect_product_links(page, log_cb)


def _collect_product_links(page, log_cb=None) -> list:
    """Extract product links from the current page."""
    product_links = []
    links = page.query_selector_all("a[href]")
    seen_urls = set()

    for link in links:
        try:
            href = link.get_attribute("href")
            text = link.inner_text().strip()

            if not href or not text:
                continue

            full_url = urljoin(BASE_URL, href)
            if re.search(r"/game/.+/[^/]+-\d{5,}$", full_url) and full_url not in seen_urls:
                seen_urls.add(full_url)
                product_links.append({"url": full_url, "title": text[:200]})
        except Exception:
            continue

    _log(log_cb, f"Found {len(product_links)} product(s)")
    return product_links


def _title_from_url(url: str) -> str:
    """Extract a readable title from a ZeusX product URL slug."""
    try:
        slug = url.rstrip("/").split("/")[-1]
        slug = re.sub(r"-\d{5,}$", "", slug)
        title = slug.replace("-", " ").strip()
        title = re.sub(r"\bor\b", "|", title, flags=re.IGNORECASE)
        return title.title()
    except Exception:
        return ""


def scrape_product_detail(page, product_url: str, log_cb=None) -> dict:
    """
    Open a product detail page and extract all relevant data:
    title, price, description, images, category info.
    """
    _log(log_cb, f"   Scraping: {product_url}")

    try:
        page.goto(product_url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, f"   WARNING: Timed out loading {product_url}")
        return {}

    # Wait for SPA content to render
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass

    _random_delay(1, 3)

    product = {"url": product_url, "scraped_at": datetime.now().isoformat()}

    # --- Title (multiple strategies) ---
    title = ""

    # Strategy 1: page title (most reliable for SPA)
    try:
        page_title = page.title()
        if page_title:
            # Remove " - ZeusX" or similar suffix
            title = re.sub(r"\s*[-|]\s*ZeusX.*$", "", page_title, flags=re.IGNORECASE).strip()
    except Exception:
        pass

    # Strategy 2: h1 element
    if not title:
        try:
            h1 = page.query_selector("h1")
            if h1:
                title = h1.inner_text().strip()
        except Exception:
            pass

    # Strategy 3: og:title meta
    if not title:
        try:
            og = page.query_selector('meta[property="og:title"]')
            if og:
                title = (og.get_attribute("content") or "").strip()
                title = re.sub(r"\s*[-|]\s*ZeusX.*$", "", title, flags=re.IGNORECASE).strip()
        except Exception:
            pass

    # Strategy 4: extract from URL slug
    if not title:
        title = _title_from_url(product_url)

    product["title"] = title

    # --- Price (multiple strategies) ---
    price = ""

    # Strategy 1: look for dollar sign in page text
    try:
        price_elements = page.query_selector_all("span, div, p")
        for el in price_elements:
            try:
                text = el.inner_text().strip()
                if "$" in text and len(text) < 20:
                    match = re.search(r"\$\s*([\d,.]+)", text)
                    if match:
                        price = match.group(1)
                        break
            except Exception:
                continue
    except Exception:
        pass

    # Strategy 2: meta tag with price
    if not price:
        try:
            meta_price = page.query_selector('meta[property="product:price:amount"], meta[property="og:price:amount"]')
            if meta_price:
                price = meta_price.get_attribute("content") or ""
        except Exception:
            pass

    product["price"] = price

    # --- Description ---
    # The Description section on ZeusX is often empty.
    # Use og:description meta as primary source (it's clean and accurate).
    try:
        meta = page.query_selector('meta[property="og:description"], meta[name="description"]')
        if meta:
            desc = (meta.get_attribute("content") or "").strip()
            # og:description often repeats the title — only keep if it adds info
            if desc and desc != title:
                product["description"] = desc
            else:
                product["description"] = ""
        else:
            product["description"] = ""
    except Exception:
        product["description"] = ""

    # --- Images (only actual product listing images) ---
    try:
        product["images"] = []
        img_elements = page.query_selector_all("img[src]")

        for img in img_elements:
            src = img.get_attribute("src") or ""
            if not src:
                continue

            # Only keep actual product offer images from ZeusX CDN
            # Skip: thumbnails (from Similar Items), user photos, tracking pixels
            if "cdn-offer-photos" not in src:
                continue
            if "_thumbnail" in src:
                continue

            full_src = urljoin(BASE_URL, src)
            if full_src not in product["images"]:
                product["images"].append(full_src)

    except Exception:
        pass

    # --- Specification fields (for re-listing) ---
    # Extract from the Specification section of the page
    try:
        page_text = page.inner_text("body")

        # Quantity (In Stock)
        stock_match = re.search(r"In Stock\s*\n?\s*(\d+)", page_text)
        if stock_match:
            product["quantity"] = int(stock_match.group(1))

        # Game name from the page breadcrumb/spec
        # The spec shows "Game" field twice - first is main game, second is sub-game
        game_matches = re.findall(r"Game\s*\n\s*(.+?)(?:\n|$)", page_text)
        if len(game_matches) >= 1:
            product["game_name"] = game_matches[0].strip()
        if len(game_matches) >= 2:
            product["sub_game"] = game_matches[1].strip()

        # Delivery time
        delivery_match = re.search(r"Estimated delivery time\s*\n?\s*(.+?)(?:\n|$)", page_text)
        if delivery_match:
            delivery_text = delivery_match.group(1).strip()
            product["delivery_time"] = delivery_text
            # Parse hours/days
            hour_match = re.search(r"(\d+)\s*Hour", delivery_text)
            day_match = re.search(r"(\d+)\s*Day", delivery_text)
            product["delivery_hours"] = int(hour_match.group(1)) if hour_match else 0
            product["delivery_days"] = int(day_match.group(1)) if day_match else 0

        # Delivery method
        method_match = re.search(r"Delivery Method\s*\n?\s*(.+?)(?:\n|$)", page_text)
        if method_match:
            product["delivery_method"] = method_match.group(1).strip()

    except Exception:
        pass

    # --- Download images locally ---
    local_images = []
    for i, img_url in enumerate(product.get("images", [])):
        try:
            ext = os.path.splitext(img_url.split("?")[0])[-1] or ".jpg"
            name_hash = hashlib.md5(img_url.encode()).hexdigest()[:10]
            safe_title = re.sub(r"[^\w]", "_", product.get("title", "product"))[:30]
            filename = f"{safe_title}_{name_hash}{ext}"
            filepath = os.path.join(IMAGES_DIR, filename)

            if not os.path.exists(filepath):
                resp = requests.get(img_url, timeout=15)
                if resp.status_code == 200:
                    with open(filepath, "wb") as f:
                        f.write(resp.content)

            local_images.append(filepath)
        except Exception:
            continue

    product["local_images"] = local_images

    _log(log_cb, f"   OK: {product.get('title', '?')} - ${product.get('price', '?')}")
    return product


def scan_all_products(headless: bool = False, log_cb=None, store_url: str = "") -> list:
    """
    Full scrape pipeline. If store_url is given, scrape from public seller page.
    Otherwise scrape from /my-listing dashboard.
    """
    _log(log_cb, "Starting full product scan...")

    with sync_playwright() as pw:
        browser, context, page = _new_context(pw, headless=headless)

        try:
            # Get product links from store URL or My Listing
            if store_url:
                product_links = scrape_store_page(page, store_url, log_cb)
            else:
                product_links = scrape_my_listings(page, log_cb)

            if not product_links:
                _log(log_cb, "WARNING: No products found on seller page")
                return []

            # Step 2: Scrape each product detail
            products = []
            for i, link in enumerate(product_links):
                _log(log_cb, f"Scraping product {i+1}/{len(product_links)}...")
                detail = scrape_product_detail(page, link["url"], log_cb)
                if detail and detail.get("title"):
                    # Mark as enabled for re-listing by default
                    detail["enabled"] = True
                    detail["last_relisted"] = None
                    products.append(detail)
                _random_delay(1, 3)

            # Save to disk
            save_products(products)
            _log(log_cb, f"Done: scanned {len(products)} products, saved to products.json")

            # Refresh session
            save_session(context)

            return products

        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════════════════════
# RE-LISTING LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def delete_listing(page, product: dict, log_cb=None) -> bool:
    """
    Delete a listing via /my-listing page.
    Flow: go to /my-listing → find listing by title → click "..." menu → Cancel Offer → Remove Listing
    """
    title = product.get("title", "")
    _log(log_cb, f"Deleting: {title}")

    try:
        page.goto(f"{BASE_URL}/my-listing", wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, "   WARNING: Could not load My Listing page")
        return False

    # Wait for page to render
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass

    _random_delay(2, 3)

    # Scroll to find the product
    for _ in range(5):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        _random_delay(1, 1.5)

    # Find the product's "..." (three-dot menu) button
    # Each listing row has a "..." menu — we need to match by title text
    try:
        # Find all listing rows/items that contain our product title
        # ZeusX listings show the title as a link text
        product_row = page.locator(f"text='{title}'").first
        if not product_row.is_visible():
            _log(log_cb, f"   WARNING: Could not find listing '{title[:50]}' on My Listing page")
            return False

        # Find the closest "..." menu button near this product
        # Navigate up to the parent container and find the menu button
        parent = product_row.locator("xpath=ancestor::*[contains(@class, 'listing') or contains(@class, 'item') or contains(@class, 'row') or self::tr or self::div[.//button]]").first

        # Look for the three-dot menu button
        menu_btn = parent.locator("button, [role='button']").last
        if menu_btn.is_visible():
            menu_btn.click()
            _random_delay(0.5, 1)
        else:
            # Fallback: just click the "..." text near the product
            dots = page.locator("text='...'").first
            if dots.is_visible():
                dots.click()
                _random_delay(0.5, 1)

    except Exception as e:
        _log(log_cb, f"   WARNING: Could not find product menu: {e}")
        return False

    # Click "Cancel Offer" from the dropdown menu
    try:
        cancel_btn = page.locator("text='Cancel Offer'").first
        cancel_btn.wait_for(timeout=5000)
        cancel_btn.click()
        _random_delay(1, 2)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not click Cancel Offer: {e}")
        return False

    # Click "Remove Listing" in the confirmation dialog
    try:
        remove_btn = page.locator("text='Remove Listing'").first
        remove_btn.wait_for(timeout=5000)
        remove_btn.click()
        _random_delay(2, 3)
        _log(log_cb, "   Listing deleted")
        return True
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not confirm removal: {e}")
        return False


def create_listing(page, product: dict, log_cb=None) -> bool:
    """
    Create a new listing on ZeusX.
    Flow: /sell → Select Category (In-Game Items) → Select Game → Fill details → Upload images → List Items
    """
    title = product.get("title", "")
    _log(log_cb, f"Creating listing: {title}")

    # Navigate to sell page - try multiple possible URLs
    sell_urls = [
        f"{BASE_URL}/sell",
        f"{BASE_URL}/create-listing",
    ]

    navigated = False
    for url in sell_urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except PlaywrightTimeout:
                pass
            # Check if we landed on a create listing page
            if "create" in page.url.lower() or "sell" in page.url.lower():
                navigated = True
                break
        except Exception:
            continue

    # Fallback: find and click "Sell" button from any page
    if not navigated:
        try:
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20_000)
            sell_link = page.locator("a:has-text('Sell'), button:has-text('Sell')").first
            if sell_link.is_visible():
                sell_link.click()
                _random_delay(2, 3)
                navigated = True
        except Exception:
            pass

    if not navigated:
        _log(log_cb, "   WARNING: Could not navigate to sell/create listing page")
        return False

    _random_delay(1, 2)

    # --- Step 1: Select Category → "In-Game Items" ---
    try:
        category_btn = page.locator("text='In-Game Items'").first
        category_btn.wait_for(timeout=10_000)
        category_btn.click()
        _log(log_cb, "   Category: In-Game Items")
        _random_delay(1, 2)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not select category: {e}")
        return False

    # --- Step 2: Select Game → search and click ---
    game_name = product.get("game_name", "Roblox In Game Items")
    try:
        # Find the search input for game
        game_search = page.locator("input[placeholder*='game' i], input[placeholder*='search' i]").first
        game_search.wait_for(timeout=10_000)
        game_search.click()
        _random_delay(0.3, 0.5)
        game_search.fill(game_name)
        _random_delay(1, 2)

        # Click the matching game result
        game_result = page.locator(f"text='{game_name}'").last
        game_result.click()
        _log(log_cb, f"   Game: {game_name}")
        _random_delay(1, 2)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not select game: {e}")
        return False

    # --- Step 3: Product Details ---

    # Title
    try:
        title_input = page.locator("input[placeholder*='title' i], input[name*='title' i]").first
        title_input.wait_for(timeout=10_000)
        title_input.click()
        title_input.fill("")
        title_input.type(title, delay=_typing_delay())
        _log(log_cb, f"   Title: {title[:50]}")
        _random_delay(0.5, 1)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not fill title: {e}")
        return False

    # Price
    price = product.get("price", "1")
    try:
        price_input = page.locator("input[placeholder*='price' i], input[name*='price' i]").first
        if price_input.is_visible():
            price_input.click()
            price_input.fill("")
            price_input.type(str(price), delay=_typing_delay())
            _log(log_cb, f"   Price: ${price}")
            _random_delay(0.5, 1)
    except Exception:
        pass

    # Multiple quantity checkbox + quantity value
    quantity = product.get("quantity", 1)
    if quantity and quantity > 1:
        try:
            # Check "Multiple quantity?" checkbox
            qty_checkbox = page.locator("text='Multiple quantity'").first
            if qty_checkbox.is_visible():
                qty_checkbox.click()
                _random_delay(0.5, 1)

                # Fill quantity input (appears after checking the box)
                qty_input = page.locator("input[type='number']").last
                if qty_input.is_visible():
                    qty_input.fill("")
                    qty_input.type(str(quantity), delay=_typing_delay())
                    _log(log_cb, f"   Quantity: {quantity}")
                    _random_delay(0.5, 1)
        except Exception:
            pass

    # Sub-game dropdown (e.g. "Sailor Piece")
    sub_game = product.get("sub_game", "")
    if sub_game:
        try:
            # Click the "Game" dropdown (under "Please select one option")
            game_dropdown = page.locator("text='Please select one option'").first
            if game_dropdown.is_visible():
                game_dropdown.click()
                _random_delay(0.5, 1)

                # Type in the search box inside the dropdown
                dropdown_search = page.locator("input[placeholder*='search' i]").last
                if dropdown_search.is_visible():
                    dropdown_search.fill(sub_game[:3])  # Type first few chars
                    _random_delay(1, 2)

                # Select the matching option
                option = page.locator(f"text='{sub_game}'").last
                if option.is_visible():
                    option.click()
                    _log(log_cb, f"   Sub-game: {sub_game}")
                    _random_delay(0.5, 1)
        except Exception:
            pass

    # Delivery Time
    delivery_days = product.get("delivery_days", 0)
    delivery_hours = product.get("delivery_hours", 1)
    try:
        # Find Days and Hours inputs
        day_inputs = page.locator("input[type='number'], input[placeholder*='day' i]")
        hour_inputs = page.locator("input[type='number'], input[placeholder*='hour' i]")

        # Look for inputs near "Days" and "Hours" labels
        days_label = page.locator("text='Days'")
        hours_label = page.locator("text='Hours'")

        if days_label.is_visible():
            days_input = days_label.locator("xpath=following::input[1]")
            if days_input.is_visible():
                days_input.fill(str(delivery_days))
                _random_delay(0.3, 0.5)

        if hours_label.is_visible():
            hours_input = hours_label.locator("xpath=following::input[1]")
            if hours_input.is_visible():
                hours_input.fill(str(delivery_hours))
                _log(log_cb, f"   Delivery: {delivery_days}d {delivery_hours}h")
                _random_delay(0.3, 0.5)
    except Exception:
        pass

    # Description (optional - many listings have none)
    desc = product.get("description", "")
    if desc:
        try:
            desc_editor = page.locator("[contenteditable='true'], textarea[placeholder*='description' i]").first
            if desc_editor.is_visible():
                desc_editor.click()
                desc_editor.type(desc, delay=_typing_delay())
                _log(log_cb, f"   Description: {len(desc)} chars")
                _random_delay(0.5, 1)
        except Exception:
            pass

    _random_delay(1, 2)

    # --- Step 4: Upload Images ---
    local_images = product.get("local_images", [])
    valid_images = [p for p in local_images if os.path.isfile(p)]
    if valid_images:
        try:
            file_input = page.locator("input[type='file']").first
            if file_input:
                file_input.set_input_files(valid_images)
                _log(log_cb, f"   Uploaded {len(valid_images)} image(s)")
                _random_delay(3, 5)  # Wait for upload processing
        except Exception as e:
            _log(log_cb, f"   WARNING: Image upload error: {e}")

    _random_delay(1, 2)

    # --- Check Terms checkbox ---
    try:
        terms_checkbox = page.locator("text='I agree'").first
        if terms_checkbox.is_visible():
            terms_checkbox.click()
            _random_delay(0.5, 1)
    except Exception:
        pass

    # --- Submit: Click "List Items" ---
    try:
        submit_btn = page.locator("button:has-text('List Items'), button:has-text('List Item')").first
        submit_btn.wait_for(timeout=5_000)
        submit_btn.click()
        _log(log_cb, "   Form submitted")
        _random_delay(3, 5)

        # Check for success or error
        try:
            # Wait a moment for response
            page.wait_for_load_state("networkidle", timeout=10_000)
        except PlaywrightTimeout:
            pass

        # Check URL or page content for success
        current_url = page.url
        if "my-listing" in current_url or "success" in current_url:
            _log(log_cb, "   Listing created successfully")
            return True

        # Check for error messages
        error_el = page.locator(".error, [class*='error' i], [class*='alert' i]").first
        try:
            if error_el.is_visible(timeout=2000):
                error_text = error_el.inner_text()
                _log(log_cb, f"   ERROR: {error_text[:200]}")
                return False
        except Exception:
            pass

        # If no error found, assume success
        _log(log_cb, "   Listing created successfully")
        return True

    except Exception as e:
        _log(log_cb, f"   WARNING: Could not submit form: {e}")
        return False


def relist_product(product: dict, headless: bool = False, log_cb=None) -> bool:
    """
    Full re-list pipeline for one product: delete old → create new.
    Returns True on success.
    """
    with sync_playwright() as pw:
        browser, context, page = _new_context(pw, headless=headless)

        try:
            # Step 1: Delete old listing
            deleted = delete_listing(page, product, log_cb)

            if not deleted:
                _log(log_cb, "   Delete failed/skipped, will still try to create new listing")

            _random_delay(2, 4)

            # Step 2: Create new listing with same data
            success = create_listing(page, product, log_cb)

            # Refresh session
            save_session(context)

            return success

        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════════════════════
# MANUAL RUN LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def run_once(
    headless: bool,
    log_cb=None,
    stop_event: threading.Event = None,
):
    """
    Manual run: Iterates through all enabled products exactly once.
    Re-lists each product (delete -> create).
    """
    if stop_event is None:
        stop_event = threading.Event()

    products = load_products()
    enabled = [p for p in products if p.get("enabled", True)]

    if not enabled:
        _log(log_cb, "WARNING: No products enabled for re-listing")
        return

    _log(log_cb, f"Bot started manual run - {len(enabled)} product(s)")

    max_retries = 3

    for idx, product in enumerate(enabled):
        if stop_event.is_set():
            _log(log_cb, "Run forcibly stopped by user.")
            break

        _log(log_cb, f"── Re-listing {idx+1}/{len(enabled)}: {product.get('title', '?')[:60]} ──")

        success = False
        for attempt in range(1, max_retries + 1):
            if stop_event.is_set():
                break

            try:
                success = relist_product(product, headless=headless, log_cb=log_cb)

                if success:
                    # Update last re-listed timestamp
                    product["last_relisted"] = datetime.now().isoformat()
                    # Persist updated product data
                    all_products = load_products()
                    for p in all_products:
                        if p.get("url") == product.get("url"):
                            p["last_relisted"] = product["last_relisted"]
                    save_products(all_products)
                    break

            except Exception as e:
                _log(log_cb, f"   ERROR: Attempt {attempt}/{max_retries}: {e}")
                if attempt < max_retries:
                    wait = 10 * attempt
                    _log(log_cb, f"   Retrying in {wait}s...")
                    _interruptible_sleep(wait, stop_event)

        if not success and not stop_event.is_set():
            _log(log_cb, "   All retries exhausted, moving to next product")

        # Small delay between products
        if not stop_event.is_set() and idx < len(enabled) - 1:
            _interruptible_sleep(5, stop_event)

    _log(log_cb, "Manual run completed.")
