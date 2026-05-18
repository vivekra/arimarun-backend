"""
Product model — defines the fixed-price infrastructure catalog.

Prices are stored in PENCE (integer) to avoid floating-point errors.
£10.00 = 1000 pence.  Display layer divides by 100.
"""
from sqlalchemy import Column, String, Integer, Boolean, JSON
from app.models.base import BaseModel


class Product(BaseModel):
    __tablename__ = "products"

    # Human-readable display name, e.g. "Basic Desktop", "VPS Small"
    name = Column(String, nullable=False)

    # Category: desktop | vps | storage | container
    resource_type = Column(String, nullable=False)

    # Fixed monthly price in PENCE.  0 = free / trial tier.
    monthly_price_pence = Column(Integer, nullable=False, default=0)

    # Fixed resource allocation delivered with this product
    cpu = Column(String, nullable=False, default="0.5")       # e.g. "1.0", "2.0"
    memory = Column(String, nullable=False, default="512m")   # e.g. "1g", "2g"
    storage_gb = Column(Integer, nullable=False, default=10)
    bandwidth_gb = Column(Integer, nullable=False, default=100)

    # Max runtime instances included in this plan
    max_instances = Column(Integer, nullable=False, default=1)

    # Soft-delete / catalogue management
    is_active = Column(Boolean, nullable=False, default=True)

    # Arbitrary extra metadata (e.g. feature flags, marketing copy)
    metadata = Column(JSON, nullable=True, default=dict)
