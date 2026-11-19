from urllib.parse import quote_plus
from bs4 import BeautifulSoup
from app.scrapers.base import BaseScraper
from flask import current_app
import time
class CromaScraper(BaseScraper):
    source="Croma"; base_url="https://www.croma.com"
    def search(self, query):
        url=f"{self.base_url}/searchB?q={quote_plus(query)}"
        html=self.fetch(url)
        if not html: return []
        results=self.parse_jsonld(html,query)
        if results: return [r for r in results if r]
        soup=BeautifulSoup(html,"html.parser"); out=[]
        for card in soup.select('[class*="product-item"], [class*="product-card"], [data-testid*="product"]'):
            title=card.select_one('h3, h2, [class*="product-title"], a[title]')
            price=card.select_one('[class*="amount"], [class*="price"]')
            link=card.select_one('a[href]')
            if not title or not price or not link: continue
            href=link.get('href',''); href=href if href.startswith('http') else self.base_url+href
            record=self.record(title.get_text(' ',strip=True),price.get_text(' ',strip=True),href,query)
            if record: out.append(record)
        return out[:20]
