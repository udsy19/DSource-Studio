from app.pricing.engine import DealerRates, QuoteLineInput, compute_quote


def _line(qty, list_price, band):
    return QuoteLineInput(
        product_id=1, manufacturer_code="SC", sku="X", name="Chair",
        qty=qty, unit_list=list_price, discount_band=band,
    )


def test_budget_math():
    # 10 chairs @ $1000 list, 50% off, install 15%, freight 3%, tax 8.63%
    rates = DealerRates(install_rate=0.15, freight_rate=0.03, tax_rate=0.0863)
    q = compute_quote([_line(10, 1000.0, 0.50)], rates)

    assert q.subtotal_list == 10000.0
    assert q.net_merchandise == 5000.0
    assert q.discount_amount == 5000.0
    assert q.install == 750.0
    assert q.freight == 150.0
    assert q.taxable_base == 5150.0                 # net + freight (install non-taxable)
    assert q.tax == round(5150.0 * 0.0863, 2)
    assert q.total == round(5000.0 + 750.0 + 150.0 + q.tax, 2)
    assert q.is_budgetary is True


def test_mixed_discount_bands():
    rates = DealerRates(0.15, 0.03, 0.08)
    lines = [_line(1, 1000.0, 0.50), _line(1, 1000.0, 0.40)]
    q = compute_quote(lines, rates)
    assert q.subtotal_list == 2000.0
    assert q.net_merchandise == 1100.0              # 500 + 600
