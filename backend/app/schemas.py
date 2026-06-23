from pydantic import BaseModel, ConfigDict


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    manufacturer_code: str
    sku: str
    name: str
    category: str
    list_price: float
    price_uom: str
    source: str


class IngestReport(BaseModel):
    kind: str  # catalog | project
    source: str
    title: str
    items_read: int
    created: int = 0
    updated: int = 0
    matched: int = 0
    project_id: int | None = None
    column_mapping: dict[str, str] | None = None
    warnings: list[str] = []


class PriceBookProductOut(BaseModel):
    base_code: str
    name: str
    configured_part_number: str
    starting_list_price: float
    step_count: int
    option_count: int
    product_id: int
    status: str


class PriceBookReport(BaseModel):
    title: str
    manufacturer_code: str
    products_parsed: int
    products: list[PriceBookProductOut] = []
    warnings: list[str] = []


class QuoteLineOut(BaseModel):
    product_id: int
    manufacturer_code: str
    sku: str
    name: str
    qty: float
    unit_list: float
    extended_list: float
    discount_band: float
    net: float


class QuoteOut(BaseModel):
    is_budgetary: bool
    disclaimer: str
    project_id: int | None = None
    project_name: str | None = None
    lines: list[QuoteLineOut]
    subtotal_list: float
    discount_amount: float
    net_merchandise: float
    install_rate: float
    freight_rate: float
    tax_rate: float
    install: float
    freight: float
    taxable_base: float
    tax: float
    total: float


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    source: str


class DealerSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    default_discount: float
    install_rate: float
    freight_rate: float
    tax_rate: float
