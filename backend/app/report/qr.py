"""QR encoding for report deliverables — a pure module→matrix step plus a canvas draw.

`qr_matrix(data)` is the pure, testable core: it returns the boolean module grid (True = dark)
via reportlab's own QR encoder, so no new dependency is introduced. `draw_qr` paints that grid onto
a report canvas in ink on paper, matching the studio palette instead of the encoder's default black.
"""

from __future__ import annotations

from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
from reportlab.pdfgen import canvas

from .palette import INK, PAPER


def qr_matrix(data: str) -> list[list[bool]]:
    """Boolean module grid for `data` (True = a dark module). Square, side == module count."""
    qr = QRCode(None, QRErrorCorrectLevel.M)  # None => auto-pick the smallest fitting version
    qr.addData(data)
    qr.make()
    n = qr.getModuleCount()
    return [[bool(qr.isDark(row, col)) for col in range(n)] for row in range(n)]


def draw_qr(c: canvas.Canvas, data: str, x: float, y: float, size: float) -> None:
    """Draw the QR for `data` as an ink-on-paper block whose bottom-left is (x, y), fitting `size`."""
    matrix = qr_matrix(data)
    n = len(matrix)
    module = size / n
    c.setFillColor(PAPER)
    c.rect(x, y, size, size, fill=1, stroke=0)
    c.setFillColor(INK)
    for row in range(n):
        for col in range(n):
            if matrix[row][col]:
                # row 0 is the top of the code; flip to page-up so it scans right-side-up.
                c.rect(x + col * module, y + (n - 1 - row) * module, module, module, fill=1, stroke=0)
