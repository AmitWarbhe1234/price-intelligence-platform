import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'price_intelligence.db'}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "12"))
    SCRAPE_DELAY_SECONDS = float(os.getenv("SCRAPE_DELAY_SECONDS", "1.0"))
    ENABLE_LIVE_SCRAPING = os.getenv("ENABLE_LIVE_SCRAPING", "true").lower() == "true"
    USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "true")
    USE_PLAYWRIGHT = os.getenv("USE_PLAYWRIGHT", "true")
    SCRAPER_DEBUG = os.getenv("SCRAPER_DEBUG", "true")