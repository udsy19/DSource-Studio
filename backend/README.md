# DSource — Backend (Phase 0: data spine)

The dealer-facing data spine: **SIF/pCon ingest → normalized catalog → budgetary quote**,
validated by **Gate A** (reproduce a known project's quote within tolerance). See `../PLAN.md`
for the full end-to-end plan; this is Phase 0.

## Why SIF
SIF (Standard Interchange Format) is the de-facto contract-furniture interchange format. The
specifiers a dealer already runs (CET Designer, Configura Spec/ProjectSpec, 2020 Worksheet)
**export** it; dealer ERPs **import** it. So the dealer hands us SIF straight from their own
tools — a legitimate data pipe with no licensed-OFML ingestion required.

## Run
```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8077      # API + docs at /docs
```
On boot it seeds the dealer config (manufacturers, discount bands, rates) and loads the
synthetic catalog via the real SIF ingest path.

## Gate A (the Phase 0 proof)
```bash
. .venv/bin/activate
python -m scripts.gate_a            # PASS/FAIL vs the dealer's "real" quote
python -m scripts.gate_a --print    # just print our computed budgetary total
pytest -q                           # 9 tests incl. SIF parse/round-trip, pricing, Gate A
```
Current synthetic result: our budgetary total **$103,044.90** vs dealer quote **$108,500** → **5.0% delta** (PASS, tolerance 15%).

## Layout
```
app/
  ingest/
    sif.py          # SIF parser + writer — the production data primitive
    pcon_excel.py   # pCon.basket Excel/CSV adapter (secondary path)
    service.py      # normalize -> upsert catalog, build projects, resolve discounts
  pricing/engine.py # budgetary quote: list - discount + install + freight + tax
  routers/          # catalog, ingest, quote, projects
  models.py         # Manufacturer, Product, Discount, DealerSettings, Project, ProjectLine
  seed.py           # dealer config (discount bands, rates)
data/synthetic/     # dealer_catalog.sif, project_alpha.sif, known_quote.json (Gate A target)
scripts/gate_a.py   # Gate A harness
```

## Real-data connector #1: manufacturer price-book PDF parser
`app/pricebook/parser.py` ingests a manufacturer's published **price-book PDF** — real list
prices, no dealer required. Key real-world finding: these PDFs are **configurators** (base model
+ numbered option "Steps" with upcharges), not flat SKU→price tables, so the parser extracts the
option tree per base model and computes a representative **starting-configuration** list price.
It emits only confidently-priced products and flags the rest (merged/odd layouts) rather than
loading wrong data. See `../docs/data-sourcing.md` for the full sourcing strategy + legal posture.

Download a real book to test against (Herman Miller publishes these publicly):
```bash
mkdir -p data/pricebooks
curl -sL -A "Mozilla/5.0" \
  https://www.hermanmiller.com/content/dam/hermanmiller/documents/pricing/PB_AEN.pdf \
  -o data/pricebooks/PB_AEN.pdf
# then ingest it:
curl -s -X POST localhost:8077/api/ingest/pricebook \
  -F manufacturer_code=HMI -F file=@data/pricebooks/PB_AEN.pdf
```
Validated: the real Aeron book yields **AER1 → $1,726** and **AER2 → $1,976** (correct real list
prices); AERE1/AER7 are flagged for review. Tests in `tests/test_pricebook.py` assert this.

## API
| Method | Path | What |
|---|---|---|
| GET  | `/api/health` | service check |
| GET  | `/api/catalog` · `/api/catalog/facets` | search/filter products |
| POST | `/api/ingest/catalog` | upload SIF/pCon → upsert catalog (`format=sif\|pcon`) |
| POST | `/api/ingest/project` | upload a BOM SIF/pCon → create a project |
| POST | `/api/ingest/pricebook` | upload a manufacturer price-book **PDF** → real list prices (`manufacturer_code`) |
| GET  | `/api/quote/project/{id}` | budgetary quote for a project |
| POST | `/api/quote` | ad-hoc quote from `{lines:[{product_id, qty}]}` |
| GET  | `/api/projects` · `/api/projects/{id}/lines` · `/api/settings` | |

## Next (Phase 0 finish + Phase 1)
- Minimal web UI (import SIF → see catalog/project → quote).
- Phase 1: floor-plate ingest (DXF/IFC) + human-confirm + program intake.
