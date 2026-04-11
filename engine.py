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
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"interval_minutes": 10, "headless": False}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)


def load_products() -> list:
    """Load saved product data from products.json."""
    if os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_products(products: list):
    """Persist product data to products.json."""
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════

def has_session() -> bool:
    """Check if auth.json exists and is valid."""
    if not os.path.exists(AUTH_FILE):
        return False
    
    try:
        with open(AUTH_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Check if has cookies
            if data.get('cookies') and len(data['cookies']) > 0:
                return True
    except:
        pass
    
    return False


def validate_session(log_cb=None) -> bool:
    """
    Validate that the session in auth.json is working by testing a page load.
    Returns True if session is valid, False otherwise.
    """
    if not has_session():
        _log(log_cb, "❌ No session file (auth.json) found")
        return False
    
    _log(log_cb, "Validating session...")
    
    try:
        with sync_playwright() as pw:
            browser, context, page = _new_context(pw, headless=True)
            
            try:
                # Try to access my-listing page (requires login)
                page.goto(f"{BASE_URL}/my-listing", wait_until="domcontentloaded", timeout=15_000)
                _random_delay(2, 3)
                
                # Check if redirected to login page (session invalid)
                current_url = page.url
                if "/login" in current_url:
                    _log(log_cb, "❌ Session expired or invalid (redirected to login)")
                    return False
                
                # Check for login form
                login_form = page.query_selector('input[type="password"], form[action*="login"]')
                if login_form:
                    _log(log_cb, "❌ Session expired or invalid (login form detected)")
                    return False
                
                # Check if we can see the listing page content
                my_listing_indicator = page.query_selector('[class*="listing"], [class*="product"], h1, .container')
                if my_listing_indicator:
                    _log(log_cb, "✅ Session is valid")
                    return True
                
                _log(log_cb, "⚠️ Could not verify session status")
                return False
                
            finally:
                browser.close()
                
    except Exception as e:
        _log(log_cb, f"❌ Error validating session: {e}")
        return False


def save_session(context):
    context.storage_state(path=AUTH_FILE)


def open_login_browser(log_cb=None):
    """
    Open ZeusX in user's default browser for manual login.
    User needs to manually copy cookies afterward.
    """
    _log(log_cb, "="*50)
    _log(log_cb, "Opening ZeusX in your default browser...")
    _log(log_cb, "⚠️ IMPORTANT: Use Email/Password to login")
    _log(log_cb, "   (Google Login will show 'insecure browser' error)")
    _log(log_cb, "="*50)
    
    webbrowser.open_new_tab(f"{BASE_URL}/login")
    
    _log(log_cb, "After login, use 'Import from Chrome' button to copy session")


def open_login_browser_manual(log_cb=None):
    """
    Open ZeusX login in a controlled Playwright browser.
    User must enter credentials MANUALLY (no auto-fill).
    Session will be saved automatically after successful login.
    """
    _log(log_cb, "="*50)
    _log(log_cb, "🌐 Opening login browser...")
    _log(log_cb, "="*50)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            # Navigate to login page
            _log(log_cb, "📍 Navigating to login page...")
            page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            
            _log(log_cb, "⏳ Please login manually...")
            _log(log_cb, "   ⚠️  Use Username/Password (NOT Google Login)")
            _log(log_cb, "   Google akan error 'This browser is not secure'")
            _log(log_cb, "   📝 Masukkan email dan password secara manual")
            
            # Wait for login (check URL change)
            logged_in = False
            for i in range(300):  # 5 minutes timeout
                current_url = page.url
                if "/my-listing" in current_url or "/dashboard" in current_url:
                    logged_in = True
                    break
                
                # Check if login form still exists (still on login page)
                try:
                    page.wait_for_selector("input[name='email'], input[type='email']", timeout=1000)
                except:
                    # Form not found, might be logged in or on different page
                    pass
                
                if i % 10 == 0 and i > 0:
                    _log(log_cb, f"   Still waiting for login... ({i}s)")
                
                page.wait_for_timeout(1000)
            
            if logged_in:
                _log(log_cb, "✅ Login detected! Saving session...")
                auth_data = _extract_auth_data(page, context)
                _save_auth(auth_data)
                _log(log_cb, "✅ Session saved successfully!")
                _log(log_cb, "You can now close the browser and start the bot.")
                
                # Keep browser open for a moment so user can see
                page.wait_for_timeout(3000)
            else:
                _log(log_cb, "❌ Login timeout - no login detected")
                
        except Exception as e:
            _log(log_cb, f"❌ Error during login: {e}")
        finally:
            browser.close()


def import_session_from_chrome(log_cb=None):
    """
    Import cookies from Chrome/Edge browser to create auth.json
    Tries multiple profiles and paths to find ZeusX cookies.
    """
    import sqlite3
    import shutil
    import tempfile
    import glob
    
    _log(log_cb, "="*50)
    _log(log_cb, "📥 Importing session from Chrome/Edge...")
    _log(log_cb, "="*50)
    _log(log_cb, "⚠️  Make sure you are LOGGED IN to ZeusX in Chrome/Edge")
    _log(log_cb, "   (Open Chrome/Edge → Go to zeusx.com → Login → Keep browser open)")
    _log(log_cb, "")
    
    home = os.path.expanduser("~")
    cookie_paths = []
    
    # Chrome paths - multiple profiles
    chrome_base = os.path.join(home, r"AppData\Local\Google\Chrome\User Data")
    if os.path.exists(chrome_base):
        # Default profile
        default_cookies = os.path.join(chrome_base, r"Default\Network\Cookies")
        if os.path.exists(default_cookies):
            cookie_paths.append(("Chrome (Default)", default_cookies))
        
        # Other profiles
        for profile in glob.glob(os.path.join(chrome_base, "Profile *")):
            cookies_file = os.path.join(profile, "Network", "Cookies")
            if os.path.exists(cookies_file):
                profile_name = os.path.basename(profile)
                cookie_paths.append((f"Chrome ({profile_name})", cookies_file))
    
    # Edge paths - multiple profiles
    edge_base = os.path.join(home, r"AppData\Local\Microsoft\Edge\User Data")
    if os.path.exists(edge_base):
        # Default profile
        default_cookies = os.path.join(edge_base, r"Default\Network\Cookies")
        if os.path.exists(default_cookies):
            cookie_paths.append(("Edge (Default)", default_cookies))
        
        # Other profiles
        for profile in glob.glob(os.path.join(edge_base, "Profile *")):
            cookies_file = os.path.join(profile, "Network", "Cookies")
            if os.path.exists(cookies_file):
                profile_name = os.path.basename(profile)
                cookie_paths.append((f"Edge ({profile_name})", cookies_file))
    
    if not cookie_paths:
        _log(log_cb, "❌ Chrome or Edge not found!")
        _log(log_cb, "   Make sure Chrome or Edge is installed")
        return False
    
    _log(log_cb, f"Found {len(cookie_paths)} browser profile(s)")
    
    all_cookies_found = []
    
    for browser_name, cookie_db in cookie_paths:
        try:
            _log(log_cb, f"\n🔍 Checking {browser_name}...")
            
            # Copy cookies to temp file (because Chrome might have it locked)
            temp_dir = tempfile.gettempdir()
            temp_cookie = os.path.join(temp_dir, f"cookies_temp_{browser_name.replace(' ', '_')}.db")
            
            try:
                shutil.copy2(cookie_db, temp_cookie)
            except Exception as copy_error:
                _log(log_cb, f"   ⚠️  Could not read (browser might be in use): {copy_error}")
                continue
            
            conn = sqlite3.connect(temp_cookie)
            cursor = conn.cursor()
            
            # Query cookies for zeusx.com domain
            try:
                cursor.execute("""
                    SELECT name, value, host_key, path, expires_utc, is_secure, is_httponly
                    FROM cookies 
                    WHERE host_key LIKE '%zeusx%'
                """)
                
                cookies = cursor.fetchall()
            except Exception as db_error:
                _log(log_cb, f"   ⚠️  Database error: {db_error}")
                cookies = []
            
            conn.close()
            
            # Cleanup temp file
            try:
                os.remove(temp_cookie)
            except:
                pass
            
            if cookies:
                _log(log_cb, f"   ✅ Found {len(cookies)} ZeusX cookie(s)!")
                all_cookies_found.extend([(browser_name, c) for c in cookies])
            else:
                _log(log_cb, f"   ❌ No ZeusX cookies found")
                
        except Exception as e:
            _log(log_cb, f"   ⚠️  Error: {e}")
            continue
    
    if not all_cookies_found:
        _log(log_cb, "\n" + "="*50)
        _log(log_cb, "❌ FAILED TO IMPORT SESSION")
        _log(log_cb, "="*50)
        _log(log_cb, "\n🔧 Troubleshooting:")
        _log(log_cb, "1. Open Chrome/Edge browser")
        _log(log_cb, "2. Go to https://www.zeusx.com")
        _log(log_cb, "3. Login with your username/password")
        _log(log_cb, "4. DON'T close the browser")
        _log(log_cb, "5. Click 'Import from Chrome/Edge' button again")
        _log(log_cb, "\n💡 Alternative: Use '▶️ Start Bot' with username/password")
        return False
    
    # Use the profile with most cookies
    best_browser = all_cookies_found[0][0]
    best_cookies = [c for b, c in all_cookies_found if b == best_browser]
    
    _log(log_cb, f"\n📊 Using session from: {best_browser}")
    
    # Convert to Playwright storage state format
    storage_state = {
        "cookies": [],
        "origins": []
    }
    
    for name, value, host_key, path, expires_utc, is_secure, is_httponly in best_cookies:
        # Convert Chrome's expires_utc (microseconds since 1601) to Unix timestamp
        if expires_utc and expires_utc != 0:
            expires = (expires_utc - 11644473600000000) / 1000000
        else:
            expires = -1
        
        cookie = {
            "name": name,
            "value": value,
            "domain": host_key,
            "path": path or "/",
            "expires": expires,
            "httpOnly": bool(is_httponly),
            "secure": bool(is_secure),
            "sameSite": "Lax"
        }
        storage_state["cookies"].append(cookie)
    
    # Save to auth.json
    try:
        with open(AUTH_FILE, 'w', encoding='utf-8') as f:
            json.dump(storage_state, f, indent=2)
        
        _log(log_cb, "\n" + "="*50)
        _log(log_cb, f"✅ SUCCESS! Session imported from {best_browser}")
        _log(log_cb, f"   Saved {len(best_cookies)} cookie(s) to auth.json")
        _log(log_cb, "="*50)
        _log(log_cb, "\n🎉 You can now start the bot!")
        return True
        
    except Exception as e:
        _log(log_cb, f"❌ Error saving session: {e}")
        return False


def _new_context(pw, headless: bool = False):
    """Create a stealth browser context, re-using auth.json if available."""
    browser = pw.chromium.launch(headless=headless, channel="chrome")
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
# CAPTCHA DETECTION & HANDLING
# ═══════════════════════════════════════════════════════════════════════════

def _detect_captcha(page) -> bool:
    """Detect if CAPTCHA is present on the page."""
    captcha_selectors = [
        # reCAPTCHA
        'iframe[src*="captcha"]', 
        'iframe[src*="recaptcha"]',
        'iframe[src*="google.com/recaptcha"]',
        '.g-recaptcha',
        '[class*="recaptcha" i]',
        '#recaptcha',
        
        # hCAPTCHA
        'iframe[src*="hcaptcha"]',
        '.h-captcha',
        '[class*="hcaptcha" i]',
        
        # Generic CAPTCHA
        '#captcha', 
        '.captcha',
        '[class*="captcha" i]',
        '[id*="captcha" i]',
        
        # Challenge/Verification indicators
        '.challenge',
        '[class*="challenge" i]',
        '.verify',
        '.verification',
        
        # Cloudflare Turnstile
        'iframe[src*="challenges.cloudflare"]',
        '.cf-turnstile',
        '[class*="turnstile" i]',
        
        # ZeusX specific (if any)
        '[data-captcha]',
    ]
    
    for sel in captcha_selectors:
        try:
            element = page.query_selector(sel)
            if element and element.is_visible():
                return True
        except Exception:
            continue
    
    # Also check page title or text for CAPTCHA indicators
    try:
        page_text = page.inner_text('body', timeout=2000)
        captcha_keywords = ['captcha', 'recaptcha', 'verify you are human', 
                           'security check', 'bot check', 'challenge']
        text_lower = page_text.lower()
        for keyword in captcha_keywords:
            if keyword in text_lower:
                return True
    except:
        pass
    
    return False


def _wait_for_captcha_solved(page, log_cb=None, stop_event=None, timeout_seconds=300):
    """
    Wait for user to solve CAPTCHA manually.
    Returns True if CAPTCHA solved, False if timeout.
    """
    _log(log_cb, "🤖 CAPTCHA detected! Waiting for manual solve...")
    _log(log_cb, "   ⚠️  Please solve the CAPTCHA in the browser window")
    _log(log_cb, "   (Click 'I'm not a robot' or complete the challenge)")
    
    # Wait for CAPTCHA to be solved (disappear from page)
    for i in range(timeout_seconds):
        if stop_event and stop_event.is_set():
            return False
        
        time.sleep(1)
        
        # Check if CAPTCHA is still present
        if not _detect_captcha(page):
            _log(log_cb, "✅ CAPTCHA solved! Continuing...")
            _random_delay(1, 2)  # Small delay after solve
            return True
        
        # Log every 10 seconds
        if i % 10 == 0 and i > 0:
            _log(log_cb, f"   Still waiting for CAPTCHA solve... ({i}s)")
            # Take screenshot every 30 seconds to show progress?
            if i % 30 == 0:
                try:
                    page.screenshot(path=f"captcha_wait_{i}s.png")
                except:
                    pass
    
    _log(log_cb, "❌ CAPTCHA solve timeout after 5 minutes")
    return False


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT SCRAPING
# ═══════════════════════════════════════════════════════════════════════════

def _click_next_page(page, log_cb=None) -> bool:
    """
    Try to click the next page button in pagination.
    Returns True if successfully clicked, False otherwise.
    """
    # Common pagination selectors
    pagination_selectors = [
        # ZeusX specific (provided by user) - only the SINGLE step arrow
        'button.pagination_arrow-right-icon__TohKC',
        'button[class*="arrow-right-icon"]',
        
        # Next button
        'a[rel="next"]',
        'button[rel="next"]',
        'a:has-text("Next")',
        'a:has-text(">")',
        'button:has-text("Next")',
        'a.pagination-next',
    ]
    
    for selector in pagination_selectors:
        try:
            # Retry loop for disabled state (e.g. while loading)
            max_retries = 3
            for attempt in range(max_retries):
                next_btn = page.query_selector(selector)
                if not next_btn or not next_btn.is_visible():
                    break # Selector not found, try next selector
                
                # Check if it's disabled
                disabled = next_btn.get_attribute("disabled") is not None or \
                           next_btn.get_attribute("aria-disabled") == "true" or \
                           "disabled" in (next_btn.get_attribute("class") or "").lower()

                if disabled:
                    if attempt < max_retries - 1:
                        _log(log_cb, f"  Next button is disabled ({selector}), waiting 2s... (Retry {attempt+1}/{max_retries})")
                        page.wait_for_timeout(2000)
                        continue
                    else:
                        _log(log_cb, f"  Next button found but remains disabled after retries ({selector})")
                        continue # Try next selector or fail
                
                _log(log_cb, f"  Clicking 'Next' using selector: {selector}")
                
                # Human-like interaction
                next_btn.scroll_into_view_if_needed()
                next_btn.hover()
                _random_delay(0.2, 0.4)
                
                # Force click to ensure SPA event triggers
                next_btn.click(force=True, timeout=5000)
                
                # We remove the dispatchEvent fallback to prevent double-clicking
                # and jumping over pages (e.g. skipping from 1 to 3).
                
                _random_delay(2, 3) # Give more time after click
                return True
        except Exception as e:
            continue
    
    return False


def _get_current_page_number(page) -> int:
    """Try to get current page number from pagination."""
    try:
        # Look for active/current page number
        active_selectors = [
            'button.pagination_active__iVvCL',
            '.pagination_pagination__DmXRJ .pagination_active__iVvCL',
            '.pagination .active',
            '.pagination .current',
            '[class*="pagination"] [class*="active"]',
            'a[class*="page"][class*="active"]',
        ]
        
        for selector in active_selectors:
            elem = page.query_selector(selector)
            if elem:
                text = elem.inner_text().strip()
                if text.isdigit():
                    return int(text)
    except:
        pass
    
    return 1


def scrape_my_listings(page, log_cb=None) -> list:
    """
    Navigate to /my-listing (logged-in dashboard) and collect all product links.
    Uses URL parameters (?page=X) for stable pagination.
    Returns a list of dicts: [{url, title}, ...]
    """
    _log(log_cb, "Scanning My Listing dashboard using URL pagination...")

    # Simplified URL as requested
    base_url = f"{BASE_URL}/my-listing"
    
    all_product_links = []
    seen_urls = set()
    max_pages = 50  # Safety limit
    empty_pages_in_a_row = 0
    
    for page_num in range(1, max_pages + 1):
        # Construct simple page URL
        target_url = f"{base_url}?page={page_num}"
        _log(log_cb, f"  🚀 Navigating to Page {page_num}: {target_url}")
        
        try:
            # Navigate directly to the page URL
            page.goto(target_url, wait_until="domcontentloaded", timeout=30_000)
            # Wait for content or skeletal loaders to disappear
            page.wait_for_timeout(3000)
            
            # Wait for any product row to appear (Crucial for dynamic loading)
            try:
                _log(log_cb, f"    ⏳ Waiting for dashboard products to load...")
                page.wait_for_selector("[class*='my-profile-table_row'], [class*='order-info'], .ant-table-row", timeout=15000)
                # Give it an extra half-second for everything to settle
                page.wait_for_timeout(1000)
            except Exception:
                _log(log_cb, f"    ⚠️  Timeout waiting for products on page {page_num}. Trying to scrape anyway...")

            # Additional scroll to ensure all elements load
            page.evaluate("window.scrollTo(0, document.body.scrollHeight/2)")
            page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _random_delay(1, 2)
            
            # Get products from current page
            page_links = _collect_product_links(page, log_cb)
            
            if not page_links:
                _log(log_cb, f"    ⚠️ No valid product listings found on page {page_num}. Ending scan.")
                break
                
            new_links = 0
            for link in page_links:
                url = link["url"]
                title = link.get("title", "Unknown Title")
                url_slug = url.rstrip('/').split('/')[-1]
                
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_product_links.append(link)
                    new_links += 1
                    _log(log_cb, f"      [NEW] {title} ({url_slug})")
                else:
                    _log(log_cb, f"      [DUP] {title} ({url_slug})")
            
            _log(log_cb, f"    Summary: Found {new_links} new product(s) on dashboard page {page_num}")
            
            # STOPSHIP: If we find 0 new links on the dashboard, it usually means 
            # we've reached the end or the server is returning duplicates.
            # Dashboard pagination is stable, so we don't need the 'empty_pages_in_a_row' buffer.
            if new_links == 0:
                _log(log_cb, "    Stopping: No new products found on this page (End of dashboard or Duplicates).")
                break

            # Small delay between jumps
            _random_delay(1, 2)

        except Exception as e:
            _log(log_cb, f"  ❌ Error loading page {page_num}: {e}")
            break
    
    _log(log_cb, f"Finished scanning. Found {len(all_product_links)} total unique products.")
    return all_product_links


def scrape_store_page(page, store_url: str, log_cb=None) -> list:
    """
    Navigate to a public seller/store page and collect all product links.
    Handles pagination to get ALL products.
    Returns a list of dicts: [{url, title}, ...]
    """
    _log(log_cb, f"Scanning store page: {store_url}")

    try:
        page.goto(store_url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, "WARNING: Store page timed out")
        return []

    _random_delay(3, 5)
    
    # Collect all products from all pages
    all_product_links = []
    seen_urls = set()
    max_pages = 50  # Safety limit
    
    for page_num in range(1, max_pages + 1):
        _log(log_cb, f"  Scanning page {page_num}...")
        
        # Scroll to load all products on current page
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _random_delay(0.5, 1)
        
        # Get products from current page
        page_links = _collect_product_links(page, log_cb)
        
        # Capture product URLs for "Page Turn" verification
        urls_before = {link["url"] for link in page_links}
        
        new_links = 0
        for link in page_links:
            url = link["url"]
            title = link.get("title", "Unknown Title")
            url_slug = url.rstrip('/').split('/')[-1]
            
            if url not in seen_urls:
                seen_urls.add(url)
                all_product_links.append(link)
                new_links += 1
                _log(log_cb, f"      [NEW] {title} ({url_slug})")
            else:
                _log(log_cb, f"      [DUP] {title} ({url_slug})")
        
        _log(log_cb, f"    Summary: Found {new_links} new product(s) on page {page_num}")
        
        # Pacing: Wait a bit before clicking Next (for slow internet/transitions)
        _log(log_cb, "  Waiting for UI stability before next page...")
        page.wait_for_timeout(4000)
        
        # Try to go to next page
        if not _click_next_page(page, log_cb):
            _log(log_cb, "  No more pages found (Next button missing or disabled)")
            break
            
        # --- VERIFY PAGE TURN ---
        # Wait until the set of products on the page changes
        # This confirms the SPA transition completed successfully.
        _log(log_cb, "  Waiting for products to refresh (Slow internet mode: 30s timeout)...")
        page_turned = False
        for i in range(60): # Try for 30 seconds (60 * 500ms)
            page.wait_for_timeout(500)
            
            # Re-collect links to see if they changed
            current_links = _collect_product_links(page, log_cb=None) 
            urls_after = {link["url"] for link in current_links}
            
            # If the set of URLs is different, the page has turned
            if urls_after and urls_after != urls_before:
                page_turned = True
                _log(log_cb, f"  ✅ Page turn confirmed after {i/2}s")
                
                # --- UI SYNC CHECK ---
                # Double-check that the UI actually shows the NEXT page number 
                # to prevent "jumping" (e.g., skips from 5 to 11).
                # We add retries because SPA UI takes time to update text classes.
                _log(log_cb, "  Verifying page number in UI...")
                expected_page = page_num + 1
                ui_page = 0
                for sync_attempt in range(10): # retry for ~5-7 seconds
                    ui_page = _get_current_page_number(page)
                    if ui_page == expected_page:
                        break
                    page.wait_for_timeout(700)
                
                if ui_page != expected_page:
                    _log(log_cb, f"  ❌ UI SYNC ERROR: Expected Page {expected_page} but UI shows Page {ui_page}. Stopping to prevent de-sync.")
                    return all_product_links
                else:
                    _log(log_cb, f"  Synced: Page {ui_page} confirmed in UI")
                break
        
        if not page_turned:
            _log(log_cb, "  ⚠️ Page content did not change after 30s. Stopping (Check connection).")
            break
    
    _log(log_cb, f"Finished scanning. Found {len(all_product_links)} total products")
    return all_product_links


def _slugify_zeusx(text: str) -> str:
    """
    Convert a product title into a ZeusX-style URL slug.
    Example: "Aizen V1 Set | Sailor Piece" -> "aizen-v1-set-or-sailor-piece"
    """
    if not text:
        return "product"
    
    # 1. Replace '|' with 'or' (ZeusX specific)
    s = text.replace('|', ' or ')
    # 2. Lowercase and remove non-alphanumeric except spaces
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    # 3. Replace spaces/hyphens with a single hyphen
    s = re.sub(r'[\s-]+', '-', s).strip('-')
    return s


def _collect_product_links(page, log_cb=None) -> list:
    """Extract product links from the current page."""
    product_links = []
    is_dashboard = "/my-listing" in page.url
    
    # 🎯 DASHBOARD (TABLE VIEW) LOGIC
    if is_dashboard:
        # Search for rows using a very broad class selector
        rows = page.query_selector_all("div[class*='my-profile-table_row'], tr, .ant-table-row")
        for row in rows:
            try:
                # 1. Extract Title (Support multiple possible selectors)
                title_elem = row.query_selector("[class*='order-info'] span, [class*='tooltip-box-text'], .title, .name")
                title = title_elem.inner_text().strip() if title_elem else ""
                
                # 2. THE ID HUNTER: Search EVERYTHING inside the row's HTML for the 8-10 digit ID
                row_html = row.inner_html()
                # Find all 8-11 digit numbers (ZeusX IDs are usually 8-9)
                all_numbers = re.findall(r"\b\d{8,11}\b", row_html)
                
                # Filter out numbers that are definitely not IDs (like quantity '20' or dates)
                # We prioritize the one that appears first or in a value/id attribute
                listing_id = None
                if all_numbers:
                    # Often the ID is the first long number in the HTML
                    listing_id = all_numbers[0]
                
                # 3. URL RECONSTRUCTION
                row_url = None
                
                # Plan A: Try to find a direct link first
                linksInRow = row.query_selector_all('a[href*="/game/"]')
                for a in linksInRow:
                    href = a.get_attribute("href")
                    if href and re.search(r"-\d{8,}$", href.split("?")[0]):
                        row_url = urljoin(BASE_URL, href).split("?")[0]
                        break
                
                # Plan B: If no link found, but we have an ID, BUILD IT!
                if not row_url and listing_id and title:
                    slug = _slugify_zeusx(title)
                    # Short form URL that ZeusX automatically redirects to full path
                    row_url = f"{BASE_URL}/game/p-{slug}-{listing_id}"
                
                if row_url:
                    product_links.append({"url": row_url, "title": title or f"Product {listing_id}"})
            except Exception:
                continue
        
        if product_links:
            _log(log_cb, f"   Captured {len(product_links)} products from dashboard rows (Aggressive Scan active)")
            return product_links

    # 🎯 FALLBACK / SELLER PAGE
    all_links = page.query_selector_all("a[href*='/game/']")
    seen_urls = set()
    
    for link in all_links:
        try:
            href = link.get_attribute("href")
            if not href: continue
            full_url = urljoin(BASE_URL, href).split("?")[0]
            if re.search(r"/game/.*-\d{8,}$", full_url):
                if full_url not in seen_urls:
                    seen_urls.add(full_url)
                    text = link.inner_text().strip() or full_url.split("/")[-1]
                    product_links.append({"url": full_url, "title": text[:200]})
        except Exception:
            continue

    _log(log_cb, f"Found {len(product_links)} product(s) via broad scan")
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

    _random_delay(2, 4)
    
    # --- ENFORCE GSTORE SELLER ---
    # Ensure that "Gstore" exists on the page (meaning the store is GStore).
    # We check multiple areas to be sure.
    try:
        # Wait a bit for the seller info section to load
        page.wait_for_timeout(2000)
        
        # Check text content of the entire body as a broad filter
        body_text = page.inner_text("body").lower()
        if "gstore" not in body_text:
            _log(log_cb, "   [SKIP] Product is not from GStore (Seller name not found)")
            return {}
    except Exception:
        pass

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
    Full scrape pipeline. If store_url is given, scrape from public seller page (no login needed).
    Otherwise scrape from /my-listing dashboard (login required).
    """
    is_public_scan = bool(store_url and store_url.strip())
    
    _log(log_cb, "="*50)
    if is_public_scan:
        _log(log_cb, "📍 PUBLIC STORE SCAN")
        _log(log_cb, f"   URL: {store_url}")
        _log(log_cb, "   ℹ️  No login required")
    else:
        _log(log_cb, "🔐 MY LISTING SCAN")
        _log(log_cb, "   ℹ️  Login required")
    _log(log_cb, "="*50)
    
    _log(log_cb, "Starting full product scan...")
    
    with sync_playwright() as pw:
        # 1. Buka browser terlebih dahulu (Chrome Channel)
        browser = pw.chromium.launch(headless=False, channel="chrome")
        w = random.randint(1280, 1920)
        h = random.randint(800, 1080)
        
        kwargs = {"viewport": {"width": w, "height": h}}
        if has_session():
            kwargs["storage_state"] = AUTH_FILE
        
        context = browser.new_context(**kwargs)
        page = context.new_page()
        if HAS_STEALTH:
            stealth_sync(page)

        # 2. Jika bukan public scan, pastikan kita login
        if not is_public_scan:
            _log(log_cb, "🔐 Checking login status for dashboard scan...")
            try:
                # Coba buka dashboard
                page.goto(f"{BASE_URL}/my-listing", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(3000)

                # Jika mental ke login atau ada form login, berarti butuh login manual
                if "/login" in page.url or page.query_selector("input[type='password']"):
                    _log(log_cb, "⚠️ Session expired or not logged in. Please login manually in the browser window.")
                    if "/login" not in page.url:
                        page.goto(f"{BASE_URL}/login")
                    
                    if not _wait_for_login_in_browser(page, log_cb, None):
                        _log(log_cb, "❌ Login failed or cancelled")
                        browser.close()
                        return []
                    
                    save_session(context)
                    _log(log_cb, "💾 Session saved and synchronized.")
                else:
                    _log(log_cb, "✅ Session active. Proceeding to scan...")
            except Exception as e:
                _log(log_cb, f"⚠️ Error during login check: {e}")
                # Fallback: tetap coba lanjut kalau mungkin
        else:
            # Public scan: tinggal buka URL-nya saja
            try:
                page.goto(store_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as e:
                _log(log_cb, f"❌ Failed to open store URL: {e}")
                browser.close()
                return []

        try:
            # Get product links from current page (now that we are logged in or on the right page)
            if store_url:
                product_links = scrape_store_page(page, store_url, log_cb)
            else:
                product_links = scrape_my_listings(page, log_cb)

            if not product_links:
                _log(log_cb, "WARNING: No products found on seller page")
                return []

            # Load existing products to avoid duplicates
            existing_products = load_products()
            existing_urls = {p.get("url") for p in existing_products if p.get("url")}
            
            _log(log_cb, f"Found {len(product_links)} products on page. Checking for new items...")

            # Step 2: Scrape each product detail
            newly_scanned = []
            for i, link in enumerate(product_links):
                url = link["url"]
                
                # Validation: Skip if already exists
                if url in existing_urls:
                    _log(log_cb, f"   [SKIP] {i+1}/{len(product_links)} Already exists: {url}")
                    continue

                _log(log_cb, f"Scraping product {i+1}/{len(product_links)}...")
                detail = scrape_product_detail(page, url, log_cb)
                if detail and detail.get("title"):
                    # Mark as enabled for re-listing by default
                    detail["enabled"] = True
                    detail["last_relisted"] = None
                    newly_scanned.append(detail)
                _random_delay(1, 3)

            # Combine and Save to disk
            products = existing_products + newly_scanned
            save_products(products)
            _log(log_cb, f"Done: added {len(newly_scanned)} new products. Total: {len(products)} products.")

            # Refresh session (only for my-listing scan)
            if not is_public_scan:
                save_session(context)
                _log(log_cb, "💾 Session refreshed")

            return products

        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════════════════════
# RE-LISTING LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def delete_listing(page, product: dict, log_cb=None, stop_event=None) -> bool:
    """
    Delete a listing via /my-listing page.
    Flow: go to /my-listing → find listing by title → click "..." menu → Cancel Offer → Remove Listing
    Handles CAPTCHA if detected.
    """
    title = product.get("title", "")
    _log(log_cb, f"Deleting: {title}")

    try:
        page.goto(f"{BASE_URL}/my-listing", wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeout:
        _log(log_cb, "   WARNING: Could not load My Listing page")
        return False

    # Check for CAPTCHA
    if _detect_captcha(page):
        _log(log_cb, "   🤖 CAPTCHA detected on My Listing page!")
        if not _wait_for_captcha_solved(page, log_cb, stop_event):
            return False

    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass

    _random_delay(1, 2)

    # Cari produk by name di /my-listing (navigasi via ?page=X)
    _log(log_cb, "   Searching for product in My Listing...")
    
    escaped_title = title.replace("'", "\\'")
    short_title = title[:25].strip()
    product_row = None
    max_pages = 50  # Maksimal 50 halaman
    
    for page_num in range(1, max_pages + 1):
        # Kalau bukan halaman 1, navigasi ke URL dengan ?page=X
        if page_num > 1:
            try:
                page.goto(f"{BASE_URL}/my-listing?page={page_num}", wait_until="domcontentloaded", timeout=15_000)
                _random_delay(1, 2)
            except:
                break
        
        # Scroll untuk load semua produk di halaman ini
        for _ in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            _random_delay(0.5, 1)
        
        # Coba cari dengan title lengkap
        product_row = page.locator(f"text='{escaped_title}'").first
        if product_row.is_visible():
            _log(log_cb, f"   Found product on page {page_num}")
            break
            
        # Coba cari dengan short title
        if short_title:
            product_row = page.get_by_text(short_title, exact=False).first
            if product_row.is_visible():
                _log(log_cb, f"   Found product (short title) on page {page_num}")
                break
        
        # Produk tidak ditemukan di halaman ini, lanjut ke halaman berikutnya
        if page_num < max_pages:
            _log(log_cb, f"   Not found on page {page_num}, checking page {page_num + 1}...")
            continue
        else:
            # Sudah halaman terakhir, produk tidak ditemukan
            _log(log_cb, f"   WARNING: Could not find listing '{title[:50]}' on any page")
            return False

    menu_btn_clicked = False
    fallback_menu_btn = None
    
    if not product_row or not product_row.is_visible():
        _log(log_cb, f"   WARNING: Could not find listing '{title[:50]}'")
        return False

    try:
        if not menu_btn_clicked:
            _log(log_cb, "   Finding menu button for this product...")
            
            # Cari container/row produk ini dengan mencari ancestor yang paling dekat
            # Coba cari parent card/row yang mengandung produk ini
            parent_selectors = [
                "xpath=ancestor::div[contains(@class, 'listing')]",
                "xpath=ancestor::div[contains(@class, 'item')]",
                "xpath=ancestor::div[contains(@class, 'card')]",
                "xpath=ancestor::tr",
                "xpath=ancestor::div[contains(@class, 'row')]",
                "xpath=..",  # parent langsung
            ]
            
            parent = None
            for sel in parent_selectors:
                try:
                    parent = product_row.locator(sel).first
                    if parent and parent.is_visible():
                        # Cek apakah parent ini punya menu button
                        test_btn = parent.locator("button[class*='more-actions-button'], button[class*='more-action-button']").first
                        if test_btn.is_visible():
                            break
                except:
                    continue
            
            if not parent or not parent.is_visible():
                parent = product_row  # fallback ke product_row sendiri
            
            # Cari menu button di dalam parent/container
            menu_btn_locator = parent.locator("button[class*='more-actions-button']").first
            if not menu_btn_locator.is_visible():
                menu_btn_locator = parent.locator("button[class*='more-action-button']").first
            if not menu_btn_locator.is_visible():
                # Cari button dengan SVG (icon tiga titik)
                menu_btn_locator = parent.locator("button:has(svg)").first
            
            if menu_btn_locator.is_visible():
                _log(log_cb, "   Clicking menu button...")
                menu_btn_locator.click()
                _random_delay(2, 3)  # Tunggu dropdown muncul
            else:
                _log(log_cb, "   WARNING: Could not find menu button for this product")
                return False

    except Exception as e:
        _log(log_cb, f"   WARNING: Could not find product menu/click it: {e}")
        return False

    # Click "Cancel Offer" from the dropdown menu
    try:
        _log(log_cb, "   Looking for Cancel Offer button...")
        # Tunggu dropdown muncul
        page.wait_for_timeout(1000)
        
        # Coba beberapa cara mencari tombol Cancel Offer
        cancel_btn = page.locator("text='Cancel Offer'").first
        if not cancel_btn.is_visible():
            # Coba dengan selector lain
            cancel_btn = page.locator("button:has-text('Cancel Offer'), a:has-text('Cancel Offer')").first
        if not cancel_btn.is_visible():
            # Coba cari di dalam dropdown/menu
            cancel_btn = page.locator("[class*='dropdown'] >> text='Cancel Offer', [class*='menu'] >> text='Cancel Offer'").first
            
        cancel_btn.wait_for(state="visible", timeout=5000)
        _log(log_cb, "   Clicking Cancel Offer...")
        cancel_btn.click()
        _random_delay(1.5, 2.5)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not click Cancel Offer: {e}")
        return False

    # Click "Remove Listing" in the confirmation dialog
    try:
        _log(log_cb, "   Looking for Remove Listing button...")
        # Tunggu dialog muncul
        page.wait_for_timeout(1000)
        
        remove_btn = page.locator("button:has-text('Remove Listing'), button[class*='success-popup_btn-primary']").first
        if not remove_btn.is_visible():
            remove_btn = page.locator("button[class*='danger'], button[class*='red']").first
            
        remove_btn.wait_for(state="visible", timeout=5000)
        _log(log_cb, "   Clicking Remove Listing...")
        remove_btn.click()
        
        # Tunggu sampai benar-benar terhapus (dialog hilang atau redirect)
        _log(log_cb, "   Waiting for deletion to complete...")
        max_wait = 10  # maksimal 10 detik
        for i in range(max_wait):
            page.wait_for_timeout(1000)
            
            # Cek apakah dialog sudah hilang
            dialog_gone = not remove_btn.is_visible()
            
            # Cek apakah sudah kembali ke my-listing
            on_my_listing = "/my-listing" in page.url
            
            # Cek apakah masih ada tombol Cancel Offer (dropdown sudah tutup)
            cancel_offer_gone = not page.locator("text='Cancel Offer'").first.is_visible()
            
            if dialog_gone or on_my_listing:
                _log(log_cb, "   ✅ Listing deleted successfully")
                _random_delay(1, 2)
                return True
                
            # Cek error
            error_msg = page.locator("[class*='error'], .alert").first
            if error_msg.is_visible():
                _log(log_cb, f"   ❌ Error during deletion")
                return False
        
        _log(log_cb, "   ⚠️ Timeout waiting for deletion confirmation")
        return False
        
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
        f"{BASE_URL}/create-offer",
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
        title_input = page.locator("xpath=//div[text()='Listing Title']/following::input").first
        if not title_input.is_visible():
            title_input = page.locator("input[placeholder*='Eg:']").first
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
        price_input = page.locator("xpath=//div[contains(@class, 'input_label__zMh1l') and contains(., 'Price')]/following::input").first
        if not price_input.is_visible():
            price_input = page.locator("input[type='text']").nth(1)  # Fallback
        
        if price_input.is_visible():
            price_input.click()
            price_input.fill("")
            price_input.type(str(price), delay=_typing_delay())
            _log(log_cb, f"   Price: ${price}")
            _random_delay(0.5, 1)
    except Exception as e:
        _log(log_cb, f"   WARNING: Could not fill price: {e}")

    # Force quantity to 20 (as requested: "don't follow previous product data")
    quantity = 20
        
    try:
        # Check "Multiple quantity?" checkbox by clicking its container
        qty_checkbox = page.locator("div.checkbox_checkbox__O5kmi:has-text('Multiple quantity?')").first
        if qty_checkbox.is_visible():
            qty_checkbox.click()
            _random_delay(0.8, 1.5)

            # Fill quantity input (appears after checking the box)
            # Cari input quantity yang placeholder-nya "Eg: 10"
            qty_input = page.locator("input[placeholder='Eg: 10']").first
            
            # Atau cari div input-wrapper dengan placeholder apa saja tapi posisinya setelah checkbox
            if not qty_input.is_visible():
                qty_input = qty_checkbox.locator("xpath=../following-sibling::*//input[contains(@placeholder, 'Eg:')]").first
                
            if not qty_input.is_visible():
                # Fallback: ambil input kedua atau yang paling masuk akal (hindari judul)
                all_inputs = page.locator("div[class*='input-wrapper'] input").all()
                if len(all_inputs) > 1:
                    qty_input = all_inputs[-1] # Usually quantity is below title/price
                
            if qty_input and qty_input.is_visible():
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
            desc_editor = page.locator("[contenteditable='true'], .ck-editor__editable").first
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
    _log(log_cb, f"   Found {len(local_images)} image(s) in product data")
    
    valid_images = []
    for p in local_images:
        # Cross-platform fix: If path contains Windows slashes or doesn't exist, try local IMAGES_DIR
        if not os.path.isfile(p):
            filename = os.path.basename(p.replace("\\", "/"))
            local_path = os.path.join(IMAGES_DIR, filename)
            if os.path.isfile(local_path):
                valid_images.append(local_path)
                continue
            _log(log_cb, f"   [DEBUG] Image not found: {p} (also checked {local_path})")
        else:
            valid_images.append(p)

    _log(log_cb, f"   Valid images on disk: {len(valid_images)}")
    
    if valid_images:
        try:
            _log(log_cb, f"   Uploading {len(valid_images)} image(s)...")
            
            # Click the upload box via file chooser to ensure React captures the event
            upload_box = page.locator("div[class*='image-upload-box']").first
            _log(log_cb, "   [DEBUG] Mengklik area <div class='image-upload-box'> untuk memilih gambar...")
            
            if upload_box.is_visible():
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    upload_box.click()
                file_chooser = fc_info.value
                file_chooser.set_files(valid_images)
            else:
                # Fallback directly to the input if box not found
                file_input = page.locator("input[type='file'][accept*='image'], input[type='file']").first
                if file_input:
                    file_input.set_input_files(valid_images)
                else:
                    _log(log_cb, "   WARNING: Could not find file input for images")

            _log(log_cb, f"   ✅ Uploaded {len(valid_images)} image(s)")
            _random_delay(3, 5)  # Wait for upload processing
            
        except Exception as e:
            _log(log_cb, f"   WARNING: Image upload error: {e}")
    else:
        _log(log_cb, "   No valid images to upload")

    _random_delay(1, 2)

    # --- Check Terms checkbox ---
    # Klik CHECKBOX-NYA, bukan text/link
    try:
        # Cari checkbox input yang ada di dalam container dengan text "I agree with"
        terms_checkbox_input = page.locator("div.checkbox_checkbox__O5kmi:has-text('I agree with') input[type='checkbox']").last
        
        if not terms_checkbox_input.is_visible():
            # Fallback: cari checkbox input dalam label "I agree with"
            terms_checkbox_input = page.locator("label:has-text('I agree with') input[type='checkbox']").last
            
        if not terms_checkbox_input.is_visible():
            # Fallback: cari semua checkbox, lalu cek yang dekat dengan "I agree with"
            checkboxes = page.locator("input[type='checkbox']").all()
            for cb in checkboxes:
                try:
                    # Cek apakah checkbox ini dekat dengan text "I agree"
                    parent = cb.locator("xpath=..")
                    if parent.is_visible() and "I agree" in (parent.inner_text() or ""):
                        terms_checkbox_input = cb
                        break
                except:
                    continue
        
        if terms_checkbox_input and terms_checkbox_input.is_visible():
            # Klik checkboxnya langsung
            terms_checkbox_input.click()
            _log(log_cb, "   Checked: I agree with terms")
            _random_delay(0.5, 1)
        else:
            # Last resort: klik container tapi usahakan jangan klik link
            # Klik di pojok kiri container (biasanya checkbox di kiri, link di kanan)
            terms_container = page.locator("div.checkbox_checkbox__O5kmi:has-text('I agree with')").last
            if terms_container.is_visible():
                terms_container.click(position={"x": 10, "y": 10})
                _log(log_cb, "   Checked: I agree with terms (container click)")
                _random_delay(0.5, 1)
    except Exception:
        pass

    # --- Submit: Click "List Items" ---
    try:
        submit_btn = page.locator("button:has-text('List Items')").first
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
                _log(log_cb, "   ❌ Delete failed. Batal membuat listing baru untuk menghindari duplikat.")
                return False

            _log(log_cb, "   ✅ Delete successful! Waiting before creating new listing...")
            _random_delay(3, 5)  # Tunggu lebih lama setelah delete

            # Step 2: Create new listing with same data
            _log(log_cb, "   Creating new listing...")
            success = create_listing(page, product, log_cb)

            # Refresh session
            save_session(context)

            return success

        finally:
            browser.close()


# ═══════════════════════════════════════════════════════════════════════════
# MANUAL RUN LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def _auto_fill_login_form(page, log_cb=None):
    """
    Auto-fill login form with credentials from config.json.
    Returns True if form was filled, False otherwise.
    """
    try:
        cfg = load_config()
        username = cfg.get("username", "").strip()
        password = cfg.get("password", "").strip()
        
        if not username or not password:
            _log(log_cb, "   ℹ️  No credentials in config.json - manual entry required")
            return False
        
        # Try to find and fill username field
        username_filled = False
        username_selectors = [
            'input[type="text"]',
            'input[name="username"]',
            'input[id*="username" i]',
            'input[placeholder*="username" i]',
            'input[name="email"]',
            'input[type="email"]',
        ]
        
        for selector in username_selectors:
            try:
                field = page.query_selector(selector)
                if field and field.is_visible():
                    field.fill(username)
                    _log(log_cb, f"   ✅ Username filled: {username}")
                    username_filled = True
                    break
            except:
                continue
        
        # Try to find and fill password field
        password_filled = False
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="password" i]',
            'input[placeholder*="password" i]',
        ]
        
        for selector in password_selectors:
            try:
                field = page.query_selector(selector)
                if field and field.is_visible():
                    field.fill(password)
                    _log(log_cb, "   ✅ Password filled")
                    password_filled = True
                    break
            except:
                continue
        
        if username_filled and password_filled:
            _log(log_cb, "   ℹ️  Form auto-filled. Please solve CAPTCHA (if any) and click Login")
            return True
        else:
            _log(log_cb, "   ⚠️  Could not auto-fill form - please enter manually")
            return False
            
    except Exception as e:
        _log(log_cb, f"   ⚠️  Error auto-filling form: {e}")
        return False


def _wait_for_login_in_browser(page, log_cb=None, stop_event=None, timeout_seconds=300):
    """
    Wait for user to login manually in the opened browser.
    Handles CAPTCHA detection - tells user to solve it manually.
    Returns True if login successful, False if timeout or stopped.
    """
    _log(log_cb, "⏳ Waiting for you to login...")
    _log(log_cb, "   ⚠️  Use Username/Password (NOT Google Login)")
    _log(log_cb, "   Google akan error 'This browser is not secure'")
    _log(log_cb, "   📝 Please enter your credentials manually and click Login")
    
    # Check for CAPTCHA
    if _detect_captcha(page):
        _log(log_cb, "   🤖 CAPTCHA detected! Please solve it...")
        if not _wait_for_captcha_solved(page, log_cb, stop_event, timeout_seconds=120):
            return False
        _log(log_cb, "   ✅ CAPTCHA solved! Now click the Login button")

    # AUTO-FILL FROM .ENV (For testing convenience)
    email = os.getenv("ZEUSX_EMAIL")
    password = os.getenv("ZEUSX_PASSWORD")
    
    if email and password:
        try:
            _log(log_cb, f"   ⌨️  Auto-filling credentials for {email}...")
            # Wait a bit for the form to be ready
            page.wait_for_selector("input[type='email'], input[placeholder*='Email']", timeout=10000)
            
            # Fill email
            page.fill("input[type='email'], input[placeholder*='Email']", email)
            page.wait_for_timeout(500)
            
            # Fill password
            page.fill("input[type='password']", password)
            page.wait_for_timeout(1000)
            
            _log(log_cb, "   ✅ Credentials filled! Solving CAPTCHA or clicking Login...")
        except Exception as e:
            _log(log_cb, f"   ⚠️  Could not auto-fill: {e}")
    
    # Now wait for login to complete
    for i in range(timeout_seconds):
        if stop_event and stop_event.is_set():
            return False
        
        time.sleep(1)
        current_url = page.url
        
        # Check if already logged in
        if "/my-listing" in current_url or "/dashboard" in current_url:
            _log(log_cb, "✅ Login detected!")
            return True
        
        # Check if CAPTCHA appeared again (sometimes happens after clicking login)
        if _detect_captcha(page):
            _log(log_cb, "🤖 CAPTCHA appeared again! Please solve it...")
            if not _wait_for_captcha_solved(page, log_cb, stop_event, timeout_seconds=120):
                return False
            _log(log_cb, "   ✅ CAPTCHA solved! Waiting for login...")
        
        # Log every 10 seconds
        if i % 10 == 0 and i > 0:
            _log(log_cb, f"   Still waiting for login... ({i}s)")
    
    _log(log_cb, "❌ Login timeout after 5 minutes")
    return False


def run_once(
    headless: bool = False,
    log_cb=None,
    stop_event: threading.Event = None,
):
    """
    Manual run: Opens browser window (like login) and re-lists all products.
    If session expired, will open login page for manual re-login.
    """
    if stop_event is None:
        stop_event = threading.Event()

    # Check if auth.json exists
    _log(log_cb, "="*50)
    _log(log_cb, "BOT STARTING - Checking session...")
    _log(log_cb, "="*50)
    
    session_valid = False
    need_login = False
    
    if has_session():
        session_valid = True
    else:
        _log(log_cb, "⚠️ No session found - will need to login")
        need_login = True
    
    products = load_products()
    enabled = [p for p in products if p.get("enabled", True)]

    if not enabled:
        _log(log_cb, "WARNING: No products enabled for re-listing")
        return

    _log(log_cb, f"Bot started - {len(enabled)} product(s) to re-list")
    _log(log_cb, "Opening browser window...")

    # Open ONE browser window for all products (like login)
    with sync_playwright() as pw:
        # Force headless=False so user can see the browser
        browser = pw.chromium.launch(headless=False, channel="chrome")
        w = random.randint(1280, 1920)
        h = random.randint(800, 1080)
        
        kwargs = {"viewport": {"width": w, "height": h}}
        
        # Only use storage_state if session is valid
        if session_valid and has_session():
            kwargs["storage_state"] = AUTH_FILE
            _log(log_cb, "✅ Using saved session")
        
        context = browser.new_context(**kwargs)
        page = context.new_page()
        if HAS_STEALTH:
            stealth_sync(page)
        
        # If need login, open login page and wait
        if need_login:
            _log(log_cb, "🌐 Opening login page...")
            page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30_000)
            
            if not _wait_for_login_in_browser(page, log_cb, stop_event):
                _log(log_cb, "❌ Login failed or cancelled")
                browser.close()
                return
            
            # Save the new session
            save_session(context)
            _log(log_cb, "💾 Session saved for future use")
        else:
            # Try to go to my-listing to verify session works
            try:
                page.goto(f"{BASE_URL}/my-listing", wait_until="domcontentloaded", timeout=15_000)
                _random_delay(2, 3)
                
                # Check if redirected to login (session actually expired)
                if "/login" in page.url:
                    _log(log_cb, "⚠️ Session expired in browser - redirecting to login...")
                    page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded", timeout=30_000)
                    
                    if not _wait_for_login_in_browser(page, log_cb, stop_event):
                        _log(log_cb, "❌ Login failed or cancelled")
                        browser.close()
                        return
                    
                    save_session(context)
                    _log(log_cb, "💾 New session saved")
            except Exception as e:
                _log(log_cb, f"⚠️ Error checking session: {e}")
        
        _log(log_cb, "✅ Ready! Starting re-listing process...")
        
        max_retries = 3

        try:
            for idx, product in enumerate(enabled):
                if stop_event.is_set():
                    _log(log_cb, "Run stopped by user.")
                    break

                _log(log_cb, f"── Re-listing {idx+1}/{len(enabled)}: {product.get('title', '?')[:60]} ──")

                success = False
                for attempt in range(1, max_retries + 1):
                    if stop_event.is_set():
                        break

                    try:
                        # Step 1: Delete old listing
                        deleted = delete_listing(page, product, log_cb)
                        if not deleted:
                            _log(log_cb, "   ❌ Delete failed. Batal membuat listing baru untuk menghindari duplikat.")
                            break
                        
                        _log(log_cb, "   ✅ Delete successful! Preparing to create new listing...")
                        _random_delay(3, 5)  # Tunggu lebih lama setelah delete

                        # Step 2: Create new listing
                        success = create_listing(page, product, log_cb)

                        if success:
                            # Update timestamp
                            product["last_relisted"] = datetime.now().isoformat()
                            products = load_products()
                            for p in products:
                                if p.get("url") == product.get("url"):
                                    p["last_relisted"] = product["last_relisted"]
                            save_products(products)
                            _log(log_cb, "✅ Product re-listed successfully!")
                            break

                    except Exception as e:
                        _log(log_cb, f"   ERROR: Attempt {attempt}/{max_retries}: {e}")
                        if attempt < max_retries:
                            wait = 10 * attempt
                            _log(log_cb, f"   Retrying in {wait}s...")
                            _interruptible_sleep(wait, stop_event)

                if not success and not stop_event.is_set():
                    _log(log_cb, "   ❌ All retries failed, moving to next product")

                # Refresh session after each product
                save_session(context)

                # Delay between products
                if not stop_event.is_set() and idx < len(enabled) - 1:
                    _interruptible_sleep(5, stop_event)

            _log(log_cb, "✅ Manual run completed!")
            
        finally:
            browser.close()
            _log(log_cb, "Browser closed.")



def run_loop(
    interval_minutes: int = 60,
    headless: bool = False,
    log_cb=None,
    stop_event: threading.Event = None,
):
    """
    Run bot in a loop with specified interval between cycles.
    Each cycle runs run_once() which opens a browser window.
    """
    if stop_event is None:
        stop_event = threading.Event()
    
    cycle_count = 0
    
    while not stop_event.is_set():
        cycle_count += 1
        _log(log_cb, f"\n{'='*50}")
        _log(log_cb, f"CYCLE #{cycle_count} STARTING")
        _log(log_cb, f"{'='*50}")
        
        # Run one cycle (opens browser, re-lists products, closes browser)
        run_once(headless=headless, log_cb=log_cb, stop_event=stop_event)
        
        if stop_event.is_set():
            break
        
        # Wait for next cycle
        _log(log_cb, f"\n⏳ Waiting {interval_minutes} minutes until next cycle...")
        _log(log_cb, f"   (Bot will open browser again when cycle starts)\n")
        
        # Sleep in small chunks to allow stopping
        sleep_seconds = interval_minutes * 60
        chunk_size = 1  # Check every second
        
        for _ in range(0, sleep_seconds, chunk_size):
            if stop_event.is_set():
                break
            time.sleep(chunk_size)
    
    _log(log_cb, "\n🛑 Bot loop stopped by user.")
