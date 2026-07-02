"""The QR util encodes data into a square, non-trivial module grid. Deterministic, no network."""

from app.report.qr import qr_matrix


def test_matrix_is_square():
    m = qr_matrix("https://dsource.app/p/42")
    assert len(m) >= 21  # smallest QR version is 21x21
    assert all(len(row) == len(m) for row in m)


def test_encodes_the_url_deterministically():
    url = "https://dsource.app/p/42"
    assert qr_matrix(url) == qr_matrix(url)  # same input -> same code
    assert qr_matrix(url) != qr_matrix("https://dsource.app/p/43")  # different input -> different code


def test_has_finder_pattern_corners():
    # A finder pattern is a 7x7 dark box in each of three corners; the top-left (0,0) module is dark.
    m = qr_matrix("hello")
    assert m[0][0] is True
    assert all(m[0][c] for c in range(7))  # top edge of the top-left finder is solid
