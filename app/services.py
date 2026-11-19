import re, unicodedata
from difflib import SequenceMatcher

def parse_price(value):
    if value is None: return None
    if isinstance(value, (int, float)): return float(value)
    raw = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", raw)
    return float(match.group()) if match else None

def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or "")).lower()
    value = value.replace("gb", " gb ").replace("tb", " tb ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())

def make_variant_id(model, storage="", colour=""):
    return "|".join([normalize_text(model), normalize_text(storage), normalize_text(colour)])

def match_score(query, product_name, storage="", colour=""):
    q = normalize_text(query)
    p = normalize_text(product_name)
    score = SequenceMatcher(None, q, p).ratio()
    if q and all(token in p for token in q.split()): score = max(score, 0.92)
    if storage and normalize_text(storage) not in p: score *= 0.82
    if colour and normalize_text(colour) not in p: score *= 0.90
    return score

def calculate_emi(principal, annual_rate, months):
    principal = max(float(principal or 0), 0)
    months = max(int(months or 1), 1)
    monthly_rate = max(float(annual_rate or 0), 0) / 1200
    if monthly_rate == 0: return round(principal / months, 2)
    factor = (1 + monthly_rate) ** months
    return round(principal * monthly_rate * factor / (factor - 1), 2)

def estimate_discount(mrp, selling):
    if not mrp or mrp <= 0: return 0
    return round(max(0, (mrp-selling)/mrp*100), 2)
