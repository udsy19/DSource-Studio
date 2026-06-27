from app.matching import MatchBands, band

BANDS = MatchBands(exact=0.9, close=0.78)


def test_at_or_above_exact_is_exact():
    assert band(0.95, BANDS) == "exact"
    assert band(0.90, BANDS) == "exact"


def test_between_close_and_exact_is_close():
    assert band(0.85, BANDS) == "close"
    assert band(0.78, BANDS) == "close"


def test_below_close_is_no_match_never_nearest():
    # The whole point of the no-fake rule: a weak top hit is reported as no match,
    # not surfaced as if it were a real product.
    assert band(0.7799, BANDS) == "no_match"
    assert band(0.4, BANDS) == "no_match"
