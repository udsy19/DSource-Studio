"""Manufacturer price-book PDF parser — the first REAL-data connector.

Key real-world finding (validated against Herman Miller's published Aeron, Setu and Embody
price books — `PB_AEN.pdf`, `PB_SET.pdf`, `PB_EMB.pdf`): a manufacturer price book is NOT a
flat (part# -> price) table. It is a **configurator**: a base model code (e.g. AER1) followed
by numbered "Steps", each listing option codes with list-price upcharges. The configured part
number is the concatenation of chosen option codes; the configured list price is the sum of
their upcharges. This mirrors exactly how the dealer tools (CET/pCon) price an article.

So this parser extracts the option tree per base model, and computes a representative
"starting configuration" list price (the cheapest option in each step) — a real, defensible
list price keyed to a real manufacturer part number. The full step/option tree is returned so
a later stage can price any specific configuration.

Layout notes grounded in the real PDFs:
  * Each product *section* opens with a header line whose LAST token is the base code with a
    trailing "!", e.g. `Work Stool AER71!`, `Aeron ESD Work Chair AERE1!`, `Arm Kit AER900!`.
    This header is the reliable product boundary — configurators do not all start at "Step 1",
    and step numbers reset mid-product because of the two-column layout, so splitting on a
    step-number reset over-fragments. We split on the header (and on a lone base-code line).
  * The spec page itself repeats the base code on a line of its own (e.g. `AER7`).
  * Several SKUs can share one spec (e.g. AER71 assembled / AER72 ready-to-assemble Work
    Stool; Setu CQN51/52/53). These appear as back-to-back base codes with no steps between
    them; we treat the extras as ALIASES and emit one priced product per alias code.

Source: Herman Miller publishes these price books publicly as PDFs at
hermanmiller.com/content/dam/hermanmiller/documents/pricing/. List prices are facts
(uncopyrightable, Feist) — we store the facts, not the book's creative layout/imagery.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

# `Step 7. Back Support Option ...`  (trailing conditional text tolerated, trimmed later)
STEP_RE = re.compile(r"^Step\s+(\d+)\.\s*(.*)$")
# `D f ully adjustable arms +$473`  /  `MG1 graphite with MicrobeCare A +$70`  /  `A a size +$1726`
# Anchored at end-of-line so a column-bleed tail (e.g. `... +$2117 Step 12. 8Z Pellicle`) does
# NOT match — we would rather miss a contaminated line than capture a wrong price.
OPTION_RE = re.compile(r"^(\S{1,6})\s+(.+?)\s+\+\$(\d[\d,]*)\s*$")
# A base-model code: 2-6 letters then 1-3 digits (AER1, AER72, AER900, AERE1, CQN51, CQND5,
# CN112). Used both as a lone line and as the trailing token of a section-header line.
_CODE = r"[A-Z]{2,6}\d{1,3}"
# a lone base-code line such as `AER1`, `AER72`, `AER72!`, `CN122!`
LONE_BASE_RE = re.compile(rf"^({_CODE})!?$")
# a product-section header whose LAST token is the base code with a trailing "!"
HEADER_BASE_RE = re.compile(rf"^(?P<name>.*?)\s*\b(?P<code>{_CODE})!$")


@dataclass
class ConfigOption:
    code: str
    label: str
    upcharge: float


@dataclass
class ConfigStep:
    number: int
    name: str
    options: list[ConfigOption] = field(default_factory=list)


@dataclass
class ParsedProduct:
    base_code: str
    name: str
    steps: list[ConfigStep] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)

    def starting_config(self) -> tuple[str, float]:
        """Representative 'starting' configuration: cheapest option per step.

        Returns (configured_part_number, list_price). Steps with no parsed options are
        skipped. The part number concatenates the chosen option codes onto the base code,
        which is how the manufacturer's real model number is formed.
        """
        codes: list[str] = []
        total = 0.0
        for step in self.steps:
            if not step.options:
                continue
            cheapest = min(step.options, key=lambda o: o.upcharge)
            codes.append(cheapest.code)
            total += cheapest.upcharge
        part_number = self.base_code + "".join(codes)
        return part_number, round(total, 2)


@dataclass
class ParsedBook:
    title: str
    products: list[ParsedProduct] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean_step_name(raw: str) -> str:
    # cut trailing conditional clauses like " For a size (A) ..." and column-bleed tails
    name = re.split(r"\s+For\s+[a-z(]", raw)[0]
    name = re.split(r"\s+\S{1,6}\s+.+?\s+\+\$", name)[0]  # drop a bled option tail
    name = re.split(r"\s+Step\s+\d+\.", name)[0]  # drop a bled step header from the next column
    return name.strip()[:60]


def _book_title(first_page_text: str) -> str:
    # e.g. "... Price Book  Aeron® Chairs  Prices effective ..."  (may be newline-separated)
    m = re.search(r"Price Book\s+(.+?)\s+Prices effective", first_page_text, re.S)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()
    for line in first_page_text.split("\n"):
        line = line.strip()
        if "®" in line or "™" in line:
            return line[:80]
    return "Price Book"


def _is_index_page(text: str) -> bool:
    # The back-of-book "Index by Product Number" / "Index: Product Number" page lists every
    # code with page references; treat it as non-spec so its codes don't reopen products.
    head = text[:200].lower()
    return "index by product number" in head or "index:" in head and "product" in head


def parse_book(source: bytes | str) -> ParsedBook:
    import pdfplumber

    opener = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(opener) as pdf:
        pages = [p.extract_text() or "" for p in pdf.pages]

    title = _book_title(pages[0] if pages else "")
    book = ParsedBook(title=title)

    products: list[ParsedProduct] = []
    current: ParsedProduct | None = None
    cur_step: ConfigStep | None = None
    # Base codes seen since the last product that has steps. The first is the primary code of
    # the upcoming spec; any extras are ALIASES (sibling SKUs sharing one spec).
    pending_bases: list[str] = []

    def _has_priced_step(p: ParsedProduct) -> bool:
        return any(s.options for s in p.steps)

    def open_boundary(code: str, *, is_header: bool) -> None:
        nonlocal current, cur_step
        # A section header (`... CODE!`) always starts a new product, even if the code repeats
        # (e.g. two different `AER900!` accessory kits). A lone code only closes the current
        # product once that product actually has a priced step — the spec pages emit a bare
        # `Step 1.` placeholder and then repeat the base code (e.g. `AER7`), and a sibling SKU
        # code (`AER72!`) can appear before the spec; neither should finalize an empty shell.
        if current is not None and (_has_priced_step(current) if not is_header else current.steps):
            if is_header or code != current.base_code:
                products.append(current)
                current = None
                cur_step = None
                pending_bases.clear()
        if code not in pending_bases:
            pending_bases.append(code)
        if current is not None and not _has_priced_step(current):
            current.base_code = pending_bases[0]
            current.aliases = pending_bases[1:].copy()
            current.name = f"{title} ({pending_bases[0]})"

    for text in pages:
        if _is_index_page(text):
            continue
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue

            hm = HEADER_BASE_RE.match(line)
            if hm:
                open_boundary(hm.group("code"), is_header=True)
                continue
            lm = LONE_BASE_RE.match(line)
            if lm:
                open_boundary(lm.group(1), is_header=False)
                continue

            sm = STEP_RE.match(line)
            if sm:
                step_no = int(sm.group(1))
                if current is None:
                    primary = pending_bases[0] if pending_bases else (
                        f"{title.split()[0]}-{len(products) + 1}"
                    )
                    current = ParsedProduct(
                        base_code=primary,
                        name=f"{title} ({primary})",
                        aliases=pending_bases[1:].copy(),
                    )
                cur_step = ConfigStep(number=step_no, name=_clean_step_name(sm.group(2)))
                current.steps.append(cur_step)
                continue

            om = OPTION_RE.match(line)
            if om and cur_step is not None:
                code, label = om.group(1), om.group(2).strip()
                # Skip textile "Price Category N" reference rows that leak through (the real
                # starting option in such steps is $0 anyway, so we lose no price).
                if code.lower() != "price" and not label.lower().startswith("category"):
                    cur_step.options.append(ConfigOption(
                        code=code, label=label,
                        upcharge=float(om.group(3).replace(",", "")),
                    ))

    if current is not None and current.steps:
        products.append(current)

    # Expand alias SKUs (sibling codes that shared one spec) into their own priced products so
    # each real model number surfaces with its starting price.
    expanded: list[ParsedProduct] = []
    for p in products:
        expanded.append(p)
        for alias in p.aliases:
            if alias == p.base_code:
                continue
            expanded.append(ParsedProduct(
                base_code=alias, name=f"{title} ({alias})", steps=p.steps,
            ))

    # Emit only confidently-parsed products; flag the rest rather than loading wrong data.
    # Skip: zero-priced (base/Size step not captured) and anomalous step counts (two
    # configurators merged because a boundary was missed) — both produce untrustworthy prices.
    MAX_PLAUSIBLE_STEPS = 16
    priced, skipped = [], []
    for p in expanded:
        _, price = p.starting_config()
        if price > 0 and len(p.steps) <= MAX_PLAUSIBLE_STEPS:
            priced.append(p)
        else:
            skipped.append(p)
    book.products = priced
    if skipped:
        book.warnings.append(
            f"Skipped {len(skipped)} product(s) needing review (zero-priced or merged "
            f"layout): {', '.join(p.base_code for p in skipped)}."
        )
    if not book.products:
        book.warnings.append("No priced configurator products were parsed — check the grammar.")
    return book
