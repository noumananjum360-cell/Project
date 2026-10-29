"""Plain data objects shared by services and UI."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Customer:
    id: int
    loyalty_id: str
    full_name: str
    phone: str
    email: str
    notes: str
    tags: str
    status: str
    vip_tier: str | None
    vip_reason: str
    vip_override_tier: str | None
    vip_override_reason: str
    is_demo: bool
    created_at: float
    updated_at: float

    @property
    def tier(self) -> str | None:
        return self.vip_override_tier or self.vip_tier

    @property
    def masked_phone(self) -> str:
        p = self.phone or ""
        return ("•" * max(0, len(p) - 4) + p[-4:]) if len(p) > 4 else p


@dataclass
class Product:
    id: int
    sku: str
    name: str
    category: str
    unit_price: int
    tax_rate_bp: int | None
    stock_qty: int
    track_stock: bool
    active: bool
    is_demo: bool


@dataclass
class CartLine:
    """What the POS screen sends. Prices come from the product catalogue, never from the screen."""
    product_id: int
    qty: int
    line_discount: int = 0            # minor units, for the whole line


@dataclass
class PricedLine:
    product_id: int | None
    sku: str
    name: str
    category: str
    qty: int
    unit_price: int
    line_discount: int
    invoice_discount_share: int
    tax_rate_bp: int
    line_tax: int
    line_total: int

    @property
    def gross(self) -> int:
        return self.qty * self.unit_price


@dataclass
class Quote:
    lines: list[PricedLine] = field(default_factory=list)
    subtotal: int = 0
    discount_total: int = 0
    invoice_discount: int = 0
    tax_total: int = 0
    total: int = 0


@dataclass
class VipTier:
    id: int
    name: str
    rank: int
    min_single_purchase: int | None
    min_rolling_spend: int | None
    window_months: int
    color: str
    active: bool
