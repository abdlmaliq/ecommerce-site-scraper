"""
jumia_scraper.py
=================
Jumia Nigeria — Electronics / Laptops Scraper
Built with Selenium WebDriver

Features:
  ✓ Headless Chrome (runs silently in the background)
  ✓ Cookie / popup banner dismissal
  ✓ Search form interaction (types into Jumia's search box)
  ✓ Lazy scroll / infinite scroll handling
  ✓ Automatic pagination (clicks through all result pages)
  ✓ Extracts: title, price, old price, discount, rating, reviews, badge, URL
  ✓ Post-scrape filters: min rating, min reviews, max price, discounted only
  ✓ Saves results to data/jumia_laptops.json

Install:
  pip install selenium webdriver-manager

Usage:
  python jumia_scraper.py
  python jumia_scraper.py --query "gaming laptop" --pages 5
  python jumia_scraper.py --query "dell laptop" --visible
"""

import json
import os
import time
import argparse
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from webdriver_manager.chrome import ChromeDriverManager

# ══════════════════════════════════════════════════════════════
#  SETTINGS — edit everything here, no separate config needed
# ══════════════════════════════════════════════════════════════

BASE_URL          = "https://www.jumia.com.ng"
OUTPUT_DIR        = "data"
OUTPUT_FILE       = f"{OUTPUT_DIR}/jumia_laptops.json"

# ── Search ─────────────────────────────────────────────────────
# Add more queries to scrape multiple searches in one run.
SEARCH_QUERIES    = [
    "laptops",
    # "gaming laptop",
    # "hp laptop",
    # "dell laptop",
    # "lenovo laptop",
]

DEFAULT_MAX_PAGES = 10      # Jumia shows ~40 products per page

# ── Browser ────────────────────────────────────────────────────
HEADLESS          = True    # Set False to watch the browser live
WINDOW_SIZE       = "1440,900"

# ── Timing (seconds) ───────────────────────────────────────────
PAGE_LOAD_WAIT    = 15      # max wait for products to appear
BETWEEN_PAGES     = 1.5     # pause between page navigations
SCROLL_STEP_WAIT  = 0.3     # pause between scroll increments
POPUP_WAIT        = 2       # seconds to scan for popups

# ── Post-scrape Filters ────────────────────────────────────────
MIN_RATING        = None    # e.g. 3.5 — drop products below this rating
MIN_REVIEWS       = None    # e.g. 10  — drop products with fewer reviews
MAX_PRICE_NGN     = None    # e.g. 500000 — drop products above ₦500,000
ONLY_DISCOUNTED   = False   # True = keep only products currently on sale
DEDUPLICATE       = True    # Remove duplicate URLs across queries

# ══════════════════════════════════════════════════════════════


# ── Driver Setup ──────────────────────────────────────────────

def build_driver(headless: bool = HEADLESS) -> webdriver.Chrome:
    """Configure and return a headless Chrome WebDriver."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={WINDOW_SIZE}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


# ── Popup / Cookie Banner Handler ─────────────────────────────

def dismiss_popups(driver: webdriver.Chrome) -> None:
    """Silently close cookie banners, modals, and app-install prompts."""
    selectors = [
        "button[data-testid='cookies-accept']",
        "button.accept-all",
        "#onetrust-accept-btn-handler",
        "button.modal-close",
        "button[aria-label='Close']",
        ".-close",
        ".-dismiss",
        "a.-close",
    ]
    for selector in selectors:
        try:
            btn = WebDriverWait(driver, POPUP_WAIT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
            btn.click()
            time.sleep(0.5)
        except (TimeoutException, NoSuchElementException,
                ElementClickInterceptedException):
            pass


# ── Search ────────────────────────────────────────────────────

def search_jumia(driver: webdriver.Chrome, query: str) -> None:
    """Open Jumia and submit a search query via the search form."""
    wait = WebDriverWait(driver, PAGE_LOAD_WAIT)

    print(f"\n>> Opening {BASE_URL} ...")
    driver.get(BASE_URL)
    time.sleep(2)
    dismiss_popups(driver)

    print(f">> Searching: '{query}' ...")
    search_input = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='q']"))
    )
    search_input.clear()
    search_input.send_keys(query)
    time.sleep(0.5)
    search_input.send_keys(Keys.RETURN)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd")))
    print("   Results loaded.\n")
    time.sleep(1.5)


# ── Scroll ────────────────────────────────────────────────────

def scroll_page(driver: webdriver.Chrome) -> None:
    """Scroll incrementally to trigger lazy-loaded product cards."""
    total  = driver.execute_script("return document.body.scrollHeight")
    vp     = driver.execute_script("return window.innerHeight")
    pos    = 0
    step   = vp // 2

    while pos < total:
        driver.execute_script(f"window.scrollTo(0, {pos});")
        time.sleep(SCROLL_STEP_WAIT)
        pos   += step
        total  = driver.execute_script("return document.body.scrollHeight")

    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)


# ── Parse Products ────────────────────────────────────────────

def parse_products(driver: webdriver.Chrome) -> list[dict]:
    """Extract all product cards from the current page."""
    products = []

    def safe(card, selector, attr=None):
        try:
            el = card.find_element(By.CSS_SELECTOR, selector)
            return el.get_attribute(attr) if attr else el.text.strip()
        except NoSuchElementException:
            return None

    for card in driver.find_elements(By.CSS_SELECTOR, "article.prd"):
        title     = safe(card, "h3.name")
        price     = safe(card, ".prc")
        old_price = safe(card, ".old")
        discount  = safe(card, ".bdg._dsct")
        rating    = safe(card, ".stars._s")
        reviews   = safe(card, ".rev")
        badge     = safe(card, ".bdg._prm")
        url       = safe(card, "a.core", attr="href")

        if url and not url.startswith("http"):
            url = BASE_URL + url
        if rating:
            rating = rating.split(" ")[0]
        if reviews:
            reviews = reviews.replace("(", "").replace(")", "").replace(",", "")

        if title:
            products.append({
                "title":     title,
                "price":     price,
                "old_price": old_price,
                "discount":  discount,
                "rating":    rating,
                "reviews":   reviews,
                "badge":     badge,
                "url":       url,
            })

    return products


# ── Pagination ────────────────────────────────────────────────

def go_to_next_page(driver: webdriver.Chrome) -> bool:
    """Click Next Page. Returns False if no next page exists."""
    try:
        btn = driver.find_element(By.CSS_SELECTOR, "a[aria-label='Next Page']")
        if "disabled" in (btn.get_attribute("class") or ""):
            return False
        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
        time.sleep(0.5)
        btn.click()
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.staleness_of(driver.find_element(By.CSS_SELECTOR, "article.prd"))
        )
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.prd"))
        )
        time.sleep(BETWEEN_PAGES)
        return True
    except (NoSuchElementException, TimeoutException,
            ElementClickInterceptedException, StaleElementReferenceException):
        return False


# ── Filters ───────────────────────────────────────────────────

def apply_filters(products: list[dict]) -> list[dict]:
    """Apply post-scrape filters defined in the SETTINGS block."""
    filtered = products

    if MIN_RATING is not None:
        filtered = [p for p in filtered
                    if p["rating"] and float(p["rating"]) >= MIN_RATING]

    if MIN_REVIEWS is not None:
        filtered = [p for p in filtered
                    if p["reviews"] and int(p["reviews"]) >= MIN_REVIEWS]

    if MAX_PRICE_NGN is not None:
        def parse_price(p):
            try:
                return float(p["price"].replace("₦", "").replace(",", "").strip())
            except Exception:
                return float("inf")
        filtered = [p for p in filtered if parse_price(p) <= MAX_PRICE_NGN]

    if ONLY_DISCOUNTED:
        filtered = [p for p in filtered if p["discount"]]

    return filtered


# ── Save ──────────────────────────────────────────────────────

def save_json(filepath: str, data: dict) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[✓] Saved → '{filepath}'")


# ── Core Scrape ───────────────────────────────────────────────

def scrape(query: str, max_pages: int, headless: bool) -> list[dict]:
    """Run the full scrape pipeline for a single query."""
    driver       = build_driver(headless=headless)
    all_products = []
    page         = 1

    try:
        search_jumia(driver, query)
        dismiss_popups(driver)

        while page <= max_pages:
            print(f"── Page {page} ─────────────────────────────────")
            scroll_page(driver)
            dismiss_popups(driver)

            products = parse_products(driver)
            print(f"   {len(products)} products found")
            all_products.extend(products)

            if not go_to_next_page(driver):
                print("   No more pages.")
                break
            page += 1

    except Exception as e:
        print(f"\n[!] Error on page {page}: {e}")
    finally:
        driver.quit()
        print("[✓] Browser closed.")

    return all_products


# ── Entry Point ───────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scrape Jumia Nigeria for laptops")
    parser.add_argument("--query",   default=None,             help="Search term (overrides SEARCH_QUERIES)")
    parser.add_argument("--pages",   default=DEFAULT_MAX_PAGES, type=int, help="Max pages per query")
    parser.add_argument("--visible", action="store_true",       help="Show browser window")
    args = parser.parse_args()

    # CLI --query overrides the SEARCH_QUERIES list
    queries   = [args.query] if args.query else SEARCH_QUERIES
    headless  = not args.visible
    start     = time.time()
    seen_urls = set()
    combined  = []

    print("=" * 52)
    print("  JUMIA LAPTOP SCRAPER")
    print(f"  Queries  : {queries}")
    print(f"  Max pages: {args.pages}")
    print(f"  Mode     : {'visible' if args.visible else 'headless'}")
    print("=" * 52)

    for q in queries:
        products = scrape(query=q, max_pages=args.pages, headless=headless)
        products = apply_filters(products)

        if DEDUPLICATE:
            before = len(products)
            products = [p for p in products
                        if p["url"] not in seen_urls and not seen_urls.add(p["url"])]
            dupes = before - len(products)
            if dupes:
                print(f"   (removed {dupes} duplicates)")

        combined.extend(products)
        print(f"   Query '{q}': {len(products)} products kept after filters\n")

    result = {
        "meta": {
            "queries":        queries,
            "site":           BASE_URL,
            "category":       "Electronics / Laptops",
            "pages_per_query": args.pages,
            "total_products": len(combined),
            "scraped_at":     datetime.now().isoformat(),
            "filters": {
                "min_rating":      MIN_RATING,
                "min_reviews":     MIN_REVIEWS,
                "max_price_ngn":   MAX_PRICE_NGN,
                "only_discounted": ONLY_DISCOUNTED,
            }
        },
        "products": combined
    }

    save_json(OUTPUT_FILE, result)
    elapsed = time.time() - start

    print("\n── Final Summary ──────────────────────────────")
    print(f"  Total products : {len(combined)}")
    print(f"  Output file    : {OUTPUT_FILE}")
    print(f"  Time elapsed   : {elapsed:.1f}s")
    print("───────────────────────────────────────────────")

    print("\nSample results:")
    for p in combined[:4]:
        disc   = f"  {p['discount']}" if p["discount"] else ""
        rating = f"  ⭐{p['rating']}" if p["rating"] else ""
        print(f"  {p['title'][:52]:<52}  {p['price']}{disc}{rating}")