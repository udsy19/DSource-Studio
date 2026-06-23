"""Gate A as a test: ingest the known project SIF, reproduce the dealer's quote in tolerance."""

import json
from pathlib import Path

from scripts.gate_a import SYNTHETIC, TOLERANCE, compute_project_total


def test_gate_a_within_tolerance():
    our_total, _ = compute_project_total(SYNTHETIC / "project_alpha.sif")
    target = json.loads((SYNTHETIC / "known_quote.json").read_text())
    dealer_total = float(target["dealer_quote_total"])
    delta = abs(our_total - dealer_total) / dealer_total
    assert delta <= TOLERANCE, f"Gate A delta {delta*100:.1f}% exceeds {TOLERANCE*100:.0f}%"


def test_end_to_end_pipeline_produces_lines():
    our_total, quote = compute_project_total(SYNTHETIC / "project_alpha.sif")
    assert our_total > 0
    assert len(quote.lines) == 9          # project_alpha has 9 line items
    assert quote.net_merchandise < quote.subtotal_list
