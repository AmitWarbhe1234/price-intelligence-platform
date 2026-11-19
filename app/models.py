from datetime import datetime, timezone
from app import db

class ProductOffer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(300), nullable=False)
    brand = db.Column(db.String(80))
    model = db.Column(db.String(180), nullable=False, index=True)
    storage = db.Column(db.String(40), default="")
    colour = db.Column(db.String(80), default="")
    variant_id = db.Column(db.String(300), index=True)
    source = db.Column(db.String(80), nullable=False, index=True)
    seller = db.Column(db.String(160))
    product_url = db.Column(db.Text)
    image_url = db.Column(db.Text)
    currency = db.Column(db.String(8), default="INR")
    mrp = db.Column(db.Float)
    selling_price = db.Column(db.Float, nullable=False)
    discount = db.Column(db.Float)
    availability = db.Column(db.String(40), default="unknown")
    rating = db.Column(db.Float)
    review_count = db.Column(db.Integer)
    offer_text = db.Column(db.Text)
    offer_type = db.Column(db.String(80))
    bank = db.Column(db.String(100))
    offer_discount = db.Column(db.Float, default=0)
    emi_available = db.Column(db.Boolean, default=False)
    emi_tenure = db.Column(db.Integer)
    emi_rate = db.Column(db.Float)
    scraped_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    crawl_id = db.Column(db.String(80), index=True)
    is_demo = db.Column(db.Boolean, default=False)

    def to_dict(self, down_payment=0, tenure=12, interest_rate=None):
        from app.services import calculate_emi
        rate = self.emi_rate if interest_rate is None else interest_rate
        eligible_discount = self.offer_discount or 0
        effective = max(0, self.selling_price - eligible_discount)
        emi = calculate_emi(max(0, effective - down_payment), rate or 0, tenure)
        return {
            "id": self.id, "product_name": self.product_name, "brand": self.brand,
            "model": self.model, "storage": self.storage, "colour": self.colour,
            "variant_id": self.variant_id, "source": self.source, "seller": self.seller,
            "product_url": self.product_url, "image_url": self.image_url,
            "currency": self.currency, "mrp": self.mrp, "selling_price": self.selling_price,
            "discount": self.discount, "availability": self.availability,
            "rating": self.rating, "review_count": self.review_count,
            "offer_text": self.offer_text, "offer_type": self.offer_type, "bank": self.bank,
            "offer_discount": eligible_discount, "effective_price": round(effective, 2),
            "emi_available": self.emi_available, "emi_tenure": tenure,
            "emi_rate": rate, "emi_monthly": emi, "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "crawl_id": self.crawl_id, "is_demo": self.is_demo
        }

class CrawlRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crawl_id = db.Column(db.String(80), unique=True, nullable=False)
    query = db.Column(db.String(250), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(30), default="running")
    source_summary = db.Column(db.JSON, default=dict)
