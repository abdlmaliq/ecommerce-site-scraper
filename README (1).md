# Jumia Laptop Scraper

A Selenium-based web scraper for extracting laptop listings from [Jumia Nigeria](https://www.jumia.com.ng).

---

## Features

- Headless Chrome automation via Selenium
- Auto-dismisses cookie banners and popups
- Submits search queries through Jumia's search form
- Scrolls pages to trigger lazy-loaded products
- Paginates automatically through all result pages
- Extracts 8 fields per product
- Saves output to a structured JSON file

---

## Requirements

- Python 3.8+
- Google Chrome installed

```bash
pip install selenium webdriver-manager
```

> `webdriver-manager` handles ChromeDriver automatically — no manual download needed.

---

## Usage

```bash
# Default run (searches "laptops", up to 10 pages)
python jumia_scraper.py

# Custom search term
python jumia_scraper.py --query "gaming laptop"

# Limit pages
python jumia_scraper.py --query "hp laptop" --pages 3

# Watch the browser in action (useful for debugging)
python jumia_scraper.py --visible
```

---

## CLI Flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--query` | string | `"laptops"` | Product search term |
| `--pages` | int | `10` | Max result pages to scrape |
| `--visible` | flag | off | Show Chrome window instead of headless |

---

## Configuration

All settings are at the top of `jumia_scraper.py` — no separate config file needed.

```python
SEARCH_QUERIES    = ["laptops"]   # add more terms for a multi-query run
DEFAULT_MAX_PAGES = 10
HEADLESS          = True          # set False to watch the browser
MIN_RATING        = None          # e.g. 3.5 — filter by minimum star rating
MIN_REVIEWS       = None          # e.g. 10  — filter by minimum review count
MAX_PRICE_NGN     = None          # e.g. 500000 — filter by max price in ₦
ONLY_DISCOUNTED   = False         # True = only return sale items
DEDUPLICATE       = True          # remove duplicate URLs across queries
```

---

## Output

Results are saved to `data/jumia_laptops.json`.

```json
{
  "meta": {
    "queries": ["laptops"],
    "site": "https://www.jumia.com.ng",
    "category": "Electronics / Laptops",
    "total_products": 198,
    "scraped_at": "2026-03-01T14:22:05"
  },
  "products": [
    {
      "title": "HP 15 Intel Core i5 8GB/512GB SSD",
      "price": "₦ 485,000",
      "old_price": "₦ 620,000",
      "discount": "-22%",
      "rating": "4",
      "reviews": "312",
      "badge": "Jumia Express",
      "url": "https://www.jumia.com.ng/..."
    }
  ]
}
```

---

## Project Structure

```
jumia-scraper/
├── jumia_scraper.py        # main scraper
├── README.md               # this file
└── data/
    └── jumia_laptops.json  # output (created on first run)
```

---

## License

MIT
