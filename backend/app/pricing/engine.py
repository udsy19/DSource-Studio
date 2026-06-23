"""Budgetary quote engine.

Per the research, manufacturer list prices are published (PDF) and EXCLUDE planning,
design, storage, and installation — those are added by the dealer. So a credible
budgetary number is:

    ext_list        = qty * unit_list
    subtotal_list   = sum(ext_list)
    net_merchandise = sum(ext_list * (1 - discount_band))     # list-minus
    install         = net_merchandise * install_rate          # labor
    freight         = net_merchandise * freight_rate
    taxable_base    = net_merchandise + freight               # install labor treated non-taxable
    tax             = taxable_base * tax_rate
    total           = net_merchandise + install + freight + tax

Discount per line resolves: line override -> manufacturer band -> dealer default.
Labeled budgetary until the dealer confirms the firm discount in their own tools.
"""

from dataclasses import dataclass

BUDGETARY_DISCLAIMER = (
    "Budgetary estimate. Merchandise is list minus the dealer's standard discount band; "
    "install, freight, and tax are modeled. Not a firm quote — confirmed by the dealer in "
    "CET / their ERP on the actual project."
)


@dataclass
class QuoteLineInput:
    product_id: int
    manufacturer_code: str
    sku: str
    name: str
    qty: float
    unit_list: float
    discount_band: float  # already resolved (line override / mfr band / dealer default)


@dataclass
class DealerRates:
    install_rate: float
    freight_rate: float
    tax_rate: float


@dataclass
class QuoteLineResult:
    product_id: int
    manufacturer_code: str
    sku: str
    name: str
    qty: float
    unit_list: float
    extended_list: float
    discount_band: float
    net: float


@dataclass
class QuoteResult:
    is_budgetary: bool
    disclaimer: str
    lines: list[QuoteLineResult]
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


def compute_quote(lines: list[QuoteLineInput], rates: DealerRates) -> QuoteResult:
    out_lines: list[QuoteLineResult] = []
    subtotal_list = 0.0
    net_merchandise = 0.0

    for ln in lines:
        ext = round(ln.qty * ln.unit_list, 2)
        net = round(ext * (1 - ln.discount_band), 2)
        subtotal_list += ext
        net_merchandise += net
        out_lines.append(
            QuoteLineResult(
                product_id=ln.product_id, manufacturer_code=ln.manufacturer_code,
                sku=ln.sku, name=ln.name, qty=ln.qty, unit_list=ln.unit_list,
                extended_list=ext, discount_band=ln.discount_band, net=net,
            )
        )

    subtotal_list = round(subtotal_list, 2)
    net_merchandise = round(net_merchandise, 2)
    discount_amount = round(subtotal_list - net_merchandise, 2)
    install = round(net_merchandise * rates.install_rate, 2)
    freight = round(net_merchandise * rates.freight_rate, 2)
    taxable_base = round(net_merchandise + freight, 2)
    tax = round(taxable_base * rates.tax_rate, 2)
    total = round(net_merchandise + install + freight + tax, 2)

    return QuoteResult(
        is_budgetary=True, disclaimer=BUDGETARY_DISCLAIMER, lines=out_lines,
        subtotal_list=subtotal_list, discount_amount=discount_amount,
        net_merchandise=net_merchandise, install_rate=rates.install_rate,
        freight_rate=rates.freight_rate, tax_rate=rates.tax_rate,
        install=install, freight=freight, taxable_base=taxable_base, tax=tax, total=total,
    )
