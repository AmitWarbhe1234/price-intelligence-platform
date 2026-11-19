from flask import Blueprint, request, jsonify, render_template, current_app
from datetime import datetime, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from app import db
from app.models import ProductOffer, CrawlRun
from app.scrapers import SCRAPERS
from app.services import match_score, calculate_emi, make_variant_id

bp = Blueprint('main', __name__)
log = logging.getLogger(__name__)


def _truthy(value):
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


@bp.get('/')
def index():
    return render_template('index.html')


@bp.get('/health')
def health():
    return jsonify({
        "status": "ok",
        "service": "price-intelligence",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@bp.post('/api/search')
def search():
    payload = request.get_json(silent=True) or request.form.to_dict()
    query = (payload.get('query') or payload.get('model') or '').strip()

    if len(query) < 2:
        return jsonify({"error": "Please enter a mobile model (at least 2 characters)."}), 400

    storage = (payload.get('storage') or '').strip()
    colour = (payload.get('colour') or '').strip()

    try:
        budget = float(payload.get('budget') or 0)
        down = float(payload.get('down_payment') or 0)
        tenure = int(payload.get('tenure') or 12)
        rate = float(payload.get('interest_rate') or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Budget, down payment, tenure and interest rate must be numbers."}), 400

    crawl_id = str(uuid4())
    run = CrawlRun(crawl_id=crawl_id, query=query, status='running', source_summary={})
    db.session.add(run)
    db.session.commit()

    offers = []
    summary = {}
    used_mock = False

    if current_app.config.get('ENABLE_LIVE_SCRAPING', True):
        # Flask's current_app is context-local. Each worker thread needs its own
        # application context before a scraper reads configuration.
        flask_app = current_app._get_current_object()
        use_mock = _truthy(flask_app.config.get('USE_MOCK_DATA', 'true'))

        def run_scraper(cls):
            """Returns (rows, error, is_mock)."""
            with flask_app.app_context():
                scraper = cls()
                rows, error = [], None

                try:
                    rows = scraper.search(query) or []
                except Exception as exc:
                    log.exception('Scraper %s failed', cls.__name__)
                    error = str(exc)

                # Live scraping returned nothing (blocked / JS-rendered / bad selectors):
                # fall back to sample data so the app and demo still work.
                if not rows and use_mock:
                    try:
                        mock_rows = scraper.load_mock(query)
                    except Exception as exc:
                        log.warning('Mock data failed for %s: %s', cls.__name__, exc)
                        mock_rows = []

                    if mock_rows:
                        for r in mock_rows:
                            r['is_demo'] = True
                        return mock_rows, error, True

                return rows, error, False

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(run_scraper, cls): cls.source for cls in SCRAPERS}

            for future in as_completed(futures):
                source = futures[future]

                try:
                    rows, error, is_mock = future.result()
                except Exception as exc:
                    rows, error, is_mock = [], str(exc), False

                summary[source] = {"count": len(rows), "error": error, "sample_data": is_mock}
                used_mock = used_mock or is_mock
                offers.extend([r for r in rows if r])

    normalized = []

    for row in offers:
        score = match_score(query, row.get('product_name', ''), storage, colour)
        if score < 0.35:
            continue

        if storage and storage.lower().replace(' ', '') not in row.get('product_name', '').lower().replace(' ', ''):
            continue

        if budget and row['selling_price'] > budget:
            continue

        row['crawl_id'] = crawl_id
        row['is_demo'] = bool(row.get('is_demo', False))
        normalized.append(row)

    # Save each source result so the price-history endpoint can show past crawls.
    for row in normalized:
        obj = ProductOffer(**{
            k: v for k, v in row.items()
            if k in ProductOffer.__table__.columns and k not in ('id', 'scraped_at')
        })
        db.session.add(obj)

    run.status = 'completed' if normalized else 'partial'
    run.completed_at = datetime.now(timezone.utc)
    run.source_summary = summary
    db.session.commit()

    results = ProductOffer.query.filter_by(crawl_id=crawl_id).all()
    data = [x.to_dict(down, tenure, rate) for x in results]
    data.sort(key=lambda x: x['effective_price'])

    if not data:
        message = "No live listings could be collected. Check source availability or try another model."
    elif used_mock:
        message = ("Live retailer pages could not be read, so some or all results are sample data "
                   "for demonstration. They are not real prices.")
    else:
        message = None

    return jsonify({
        "query": query,
        "crawl_id": crawl_id,
        "results": data,
        "sources": summary,
        "best_deal": data[0] if data else None,
        "sample_data": used_mock,
        "message": message,
        "emi_note": "EMI is an estimate. Bank eligibility, fees and offer stacking must be verified with the retailer.",
    })


@bp.get('/api/product/<int:product_id>')
def product_detail(product_id):
    item = db.session.get(ProductOffer, product_id)
    if not item:
        return jsonify({"error": "Product offer not found"}), 404
    return jsonify(item.to_dict())


@bp.get('/api/offers/<int:product_id>')
def offer_detail(product_id):
    item = db.session.get(ProductOffer, product_id)
    if not item:
        return jsonify({"error": "Offer not found"}), 404
    return jsonify({
        "product_id": item.id,
        "offer_text": item.offer_text,
        "offer_type": item.offer_type,
        "bank": item.bank,
        "offer_discount": item.offer_discount,
        "emi_available": item.emi_available,
        "emi_tenure": item.emi_tenure,
        "emi_rate": item.emi_rate,
    })


@bp.get('/api/price-history/<int:product_id>')
def price_history(product_id):
    item = db.session.get(ProductOffer, product_id)
    if not item:
        return jsonify({"error": "Product offer not found"}), 404

    rows = (ProductOffer.query
            .filter_by(variant_id=item.variant_id, source=item.source)
            .order_by(ProductOffer.scraped_at.asc())
            .all())

    return jsonify({
        "product_id": product_id,
        "source": item.source,
        "history": [{"price": r.selling_price, "scraped_at": r.scraped_at.isoformat()} for r in rows],
    })


@bp.post('/api/emi')
def emi():
    data = request.get_json(silent=True) or {}

    try:
        principal = float(data.get('price', 0)) - float(data.get('down_payment', 0))
        months = int(data.get('tenure', 12))
        rate = float(data.get('interest_rate', 0))
        if principal < 0 or months < 1 or months > 60 or rate < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"error": "Provide valid price, down_payment, tenure (1-60), and interest_rate."}), 400

    monthly = calculate_emi(principal, rate, months)

    return jsonify({
        "financed_amount": round(principal, 2),
        "monthly_emi": monthly,
        "total_repayment": round(monthly * months, 2),
        "total_interest": round(monthly * months - principal, 2),
        "assumption": "Reducing-balance monthly interest; estimate only.",
    })
