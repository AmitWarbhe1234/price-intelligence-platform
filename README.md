# PriceIntel — E-commerce Price Intelligence Platform

A Flask-based smartphone price comparison technical assessment project. It searches Croma, Vijay Sales and Reliance Digital, normalizes returned product listings, compares prices and estimates EMI. SQLite is the zero-configuration default; PostgreSQL is supported through `DATABASE_URL`.

## Features
- Search by phone model with optional storage, colour and maximum budget.
- Three independent retailer adapters (Croma, Vijay Sales, Reliance Digital).
- JSON-LD Product/Offer extraction first, with conservative HTML-card fallback selectors.
- Partial results: a failure at one retailer does not fail the whole search.
- INR price parsing, variant key generation, approximate product matching and price ranking.
- Indicative reducing-balance EMI calculator with down payment, tenure and annual interest rate.
- Persistent crawl metadata and price snapshots; product, offer and price-history endpoints.
- Responsive Flask frontend, tests, Docker Compose and environment-based configuration.

## Requirements
- Python 3.10+ (tested design target: Python 3.12)
- Internet access for live retailer pages
- Optional: Docker Desktop for PostgreSQL + Docker deployment

## Run locally on Windows (PowerShell)
```powershell
# Extract ZIP and open the extracted project folder in VS Code
py -3.12 -m venv venv
.env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python run.py
```
Open **http://127.0.0.1:5000**. If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate again. You can also run `venv\Scripts\python.exe run.py` without activating.

## Run tests
```powershell
pytest -q
```
Tests disable live scraping and use a temporary SQLite database.

## Run with Docker + PostgreSQL
```bash
docker compose up --build
```
Open http://localhost:5000. Stop with `docker compose down`; add `-v` only if you also want to delete the PostgreSQL volume/data.

## API
### `GET /`
Flask search dashboard.

### `GET /health`
Service health check.

### `POST /api/search`
```json
{
  "query": "iPhone 17 Pro",
  "storage": "256 GB",
  "colour": "",
  "budget": 140000,
  "down_payment": 20000,
  "tenure": 12,
  "interest_rate": 0
}
```
Returns sorted `results`, source-level status, `crawl_id`, and `best_deal` where listings were collected.

### `POST /api/emi`
```json
{"price": 129490, "down_payment": 20000, "tenure": 12, "interest_rate": 12}
```
Returns financed amount, estimated monthly EMI, total repayment and interest.

### `GET /api/product/<id>`
Returns a stored offer record.

### `GET /api/offers/<id>`
Returns offer fields captured for a stored listing.

### `GET /api/price-history/<id>`
Returns stored price snapshots for the same variant/source across crawls.

## Architecture
`routes.py` coordinates request validation, bounded three-worker source collection, filtering, persistence and ranking. Each adapter inherits `BaseScraper`; it fetches a retailer search page with a timeout, attempts schema.org JSON-LD extraction, then falls back to retailer-specific card selectors. `services.py` contains parsing, matching and EMI calculations. SQLAlchemy models store offer snapshots and crawl run metadata.

## Scraping, compliance and limitations
- The adapters use ordinary public search pages and do not bypass login, CAPTCHA, bot checks or access controls.
- Retailer markup, endpoints, availability and terms change. A retailer may return HTTP 403/429, require JavaScript, or expose no parseable product data. The app reports that source as unavailable and continues with other sources.
- Before production use, review each retailer's current robots.txt, terms and permitted access rules, and obtain permission/API access where required. Use conservative request frequency. Do not deploy this as a high-volume crawler.
- HTML selectors are best-effort fallback selectors, not a guarantee of live extraction. JSON-LD is preferred when present.
- Product matching is approximate and should be manually validated for exact SKU/colour/storage. A retailer title that omits a variant cannot prove an exact match.
- Bank/exchange offers are not assumed combinable. The current adapter captures offer data only where product JSON-LD or page fields make it available; dedicated bank-offer pages are not blindly applied to all products.
- EMI is a mathematical estimate. It is not a bank quote and excludes processing fees, taxes, card eligibility and promotional cashback timing. A 0% rate means a simple principal/tenure estimate, not a verified no-cost EMI promotion.
- If no live listings are available, the UI explicitly shows no results; it does not fabricate sample prices.

## Configuration
Copy `.env.example` to `.env`. `DATABASE_URL` accepts SQLite or PostgreSQL SQLAlchemy URLs. `REQUEST_TIMEOUT` controls retailer request timeout. `ENABLE_LIVE_SCRAPING=false` is useful for offline smoke tests.

## Submission checklist
- [x] Flask UI and JSON API
- [x] Three retailer adapters
- [x] Product/variant normalization and price comparison
- [x] EMI calculation
- [x] Persistent scrape timestamps and price history endpoint
- [x] Partial source failure handling and logging
- [x] Tests and README
- [x] Docker Compose + PostgreSQL configuration
- [ ] Verify current retailer selectors and permitted access on the evaluator's network



A sample SQLite database (price_intelligence.db) and sample listings (app/data/mock_listings.json) are included.
