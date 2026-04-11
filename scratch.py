from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://zeusx.com/seller/gstore-657837", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    links = page.query_selector_all("a[href]")
    for link in links:
        href = link.get_attribute("href")
        print(href)
    browser.close()
