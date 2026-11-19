import json
import logging
import os
import re
import time

import requests
from bs4 import BeautifulSoup
from flask import current_app

from app.services import parse_price, make_variant_id, estimate_discount

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}


def _cfg(key, default=None):
    """Read a config value safely (works inside and outside app context)."""
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        return default


def _truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class BaseScraper:
    source = "Retailer"
    search_url = ""
    base_url = ""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(BROWSER_HEADERS)

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    def fetch(self, url, render=False):
        """
        Return page HTML.

        1. Plain requests first (fast).
        2. If blocked (403/429) or request fails, and Playwright fallback is
           enabled (config USE_PLAYWRIGHT=true), retry with a headless browser.
        3. render=True skips requests and goes straight to Playwright
           (use for JavaScript-rendered pages).

        The HTML is saved to debug/<ScraperName>.html when SCRAPER_DEBUG=true
        so you can inspect what the server actually returned.
        """
        use_playwright = _truthy(_cfg("USE_PLAYWRIGHT", False))

        if render:
            html = self.fetch_rendered(url)
            self._debug_dump(html)
            return html

        timeout = _cfg("REQUEST_TIMEOUT", 12)
        error_message = None

        try:
            response = self.session.get(url, timeout=timeout)

            if response.status_code in (403, 404, 429, 503):
                error_message = (
                    f"{self.source} returned HTTP {response.status_code}. "
                    "The retailer may be blocking automated requests "
                    "or the search page may be unavailable."
                )
            else:
                response.raise_for_status()
                html = response.text
                self._debug_dump(html)
                return html

        except requests.RequestException as exc:
            error_message = f"{self.source} request failed: {exc}"

        log.warning("%s", error_message)

        if use_playwright:
            log.info("%s: retrying with Playwright", self.source)
            try:
                html = self.fetch_rendered(url)
                self._debug_dump(html)
                return html
            except Exception as exc:  # noqa: BLE001
                error_message = f"{error_message} | Playwright failed: {exc}"
                log.warning("%s", error_message)

        raise RuntimeError(error_message)

    def fetch_rendered(self, url, wait_selector=None):
        """Fetch a page using a headless Chromium browser (renders JavaScript)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright is not installed. Run: pip install playwright "
                "&& playwright install chromium"
            ) from exc

        timeout_ms = int(_cfg("PLAYWRIGHT_TIMEOUT", 30)) * 1000

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-IN",
                    viewport={"width": 1366, "height": 800},
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=timeout_ms)
                    except Exception:  # noqa: BLE001
                        log.info("%s: selector %s not found", self.source, wait_selector)
                else:
                    try:
                        page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    except Exception:  # noqa: BLE001
                        pass

                # small scroll to trigger lazy-loaded product cards
                page.mouse.wheel(0, 1500)
                time.sleep(1)

                return page.content()
            finally:
                browser.close()

    def fetch_json(self, url, params=None, headers=None):
        """Fetch a JSON API endpoint (use when you find the site's internal API)."""
        timeout = _cfg("REQUEST_TIMEOUT", 12)
        merged = dict(self.session.headers)
        merged["Accept"] = "application/json, text/plain, */*"
        if headers:
            merged.update(headers)

        try:
            response = self.session.get(
                url, params=params, headers=merged, timeout=timeout
            )
            if response.status_code in (403, 404, 429, 503):
                raise RuntimeError(
                    f"{self.source} API returned HTTP {response.status_code}."
                )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            message = f"{self.source} JSON request failed: {exc}"
            log.warning("%s", message)
            raise RuntimeError(message) from exc

    def _debug_dump(self, html):
        """Save raw HTML to debug/<ScraperName>.html when SCRAPER_DEBUG is on."""
        if not _truthy(_cfg("SCRAPER_DEBUG", True)):
            return
        try:
            project_root = os.path.dirname(current_app.root_path)
            folder = os.path.join(project_root, "debug")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"{self.__class__.__name__}.html")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html or "")
            log.info("%s: saved HTML to %s (%d chars)", self.source, path, len(html or ""))
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not write debug HTML: %s", exc)

    # ------------------------------------------------------------------
    # Mock fallback
    # ------------------------------------------------------------------
    def load_mock(self, query):
        """
        Return sample listings for this retailer from app/data/mock_listings.json.

        File format:
        {
          "Croma": [
            {"name": "Apple iPhone 17 Pro 256GB", "price": 129900,
             "mrp": 134900, "url": "https://www.croma.com/", "brand": "Apple",
             "availability": "instock", "offer_text": "5% instant discount",
             "offer_type": "bank"}
          ],
          "Reliance Digital": [...],
          "Vijay Sales": [...]
        }
        """
        path = os.path.join(current_app.root_path, "data", "mock_listings.json")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            log.warning("Mock data unavailable: %s", exc)
            return []

        results = []
        for item in data.get(self.source, []):
            record = self.record(
                item.get("name", query),
                item.get("price"),
                item.get("url", ""),
                query,
                brand=item.get("brand", ""),
                mrp=item.get("mrp"),
                availability=item.get("availability", "instock"),
                image=item.get("image"),
            )
            if record:
                record["offer_text"] = item.get("offer_text", "")
                record["offer_type"] = item.get("offer_type", "")
                record["source"] = f"{self.source} (sample)"
                results.append(record)
        return results

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def search(self, query):
        raise NotImplementedError

    def parse_jsonld(self, html, query):
        soup = BeautifulSoup(html, "html.parser")
        found = []
        seen = set()

        page_text = soup.get_text(" ", strip=True)

        offer_match = re.search(
            r"(?:bank offer|instant discount|cashback|no cost emi|exchange offer)[^.!]{0,180}",
            page_text,
            re.I,
        )
        offer_text = offer_match.group(0) if offer_match else ""
        lowered = offer_text.lower()

        offer_type = (
            "emi" if "emi" in lowered
            else "bank" if "bank" in lowered or "discount" in lowered
            else "exchange" if "exchange" in lowered
            else ""
        )

        for node in soup.select('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.string or node.get_text())
            except (ValueError, TypeError):
                continue

            objects = data if isinstance(data, list) else [data]
            index = 0

            while index < len(objects):
                obj = objects[index]
                index += 1

                if not isinstance(obj, dict):
                    continue

                graph = obj.get("@graph")
                if isinstance(graph, list):
                    objects.extend(graph)

                obj_type = obj.get("@type")
                types = obj_type if isinstance(obj_type, list) else [obj_type]

                # Search pages often expose products as an ItemList
                if "ItemList" in types:
                    for element in obj.get("itemListElement", []) or []:
                        if isinstance(element, dict):
                            objects.append(element.get("item", element))
                    continue

                if "Product" not in types:
                    continue

                offers = obj.get("offers", {})
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                if not isinstance(offers, dict):
                    continue

                price = parse_price(offers.get("price") or offers.get("lowPrice"))
                if not price:
                    continue

                name = obj.get("name", query)
                url = obj.get("url") or offers.get("url") or ""

                if url.startswith("/"):
                    url = self.base_url + url

                key = (str(name).lower(), url)
                if key in seen:
                    continue
                seen.add(key)

                brand = obj.get("brand", "")
                if isinstance(brand, dict):
                    brand = brand.get("name", "")

                availability = (
                    str(offers.get("availability", "unknown"))
                    .split("/")[-1]
                    .replace(" ", "_")
                    .lower()
                )

                image = obj.get("image")
                if isinstance(image, list):
                    image = image[0] if image else None
                if isinstance(image, dict):
                    image = image.get("url")

                record = self.record(
                    name,
                    price,
                    url,
                    query,
                    brand=brand,
                    availability=availability,
                    image=image,
                )

                if record:
                    record["offer_text"] = offer_text
                    record["offer_type"] = offer_type
                    found.append(record)

        return found

    def record(
        self,
        name,
        price,
        url,
        query,
        brand="",
        mrp=None,
        availability="unknown",
        image=None,
    ):
        price = parse_price(price)
        mrp = parse_price(mrp) or price

        if not price:
            return None

        return {
            "product_name": str(name),
            "brand": brand or str(name).split()[0],
            "model": query,
            "storage": "",
            "colour": "",
            "variant_id": make_variant_id(name),
            "source": self.source,
            "seller": self.source,
            "product_url": url,
            "image_url": image if isinstance(image, str) else None,
            "currency": "INR",
            "mrp": mrp,
            "selling_price": price,
            "discount": estimate_discount(mrp, price),
            "availability": availability,
            "offer_text": "",
            "offer_type": "",
            "bank": "",
            "offer_discount": 0,
            "emi_available": False,
            "emi_tenure": None,
            "emi_rate": 0,
        }
