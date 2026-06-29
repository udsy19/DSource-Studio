from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, SessionLocal, engine
from .ingest import service
from .models import ensure_catalog_columns
from .ingest.sif import parse_sif
from .procurement.models import seed_vendors
from .realdata import apply_coop_hmi_band, ingest_hm_pricebooks
from .routers import (
    alternatives, brief, cad, catalog, coop, floorplan, floorplan_raster, generate,
    generate_detailed, gsa, ifc, ingest, ingest_cad, ingest_raster, layout_takeoff, library, match,
    procurement, projects, quote, render, report, source, takeoff, testfit, version_export,
    wellcatalog,
)
from .seed import seed
from .wellcatalog.seed import seed_certs

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def bootstrap() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_catalog_columns(engine)  # in-place add of India-catalog columns to an existing db
    db = SessionLocal()
    try:
        seed(db)
        # Load the synthetic catalog via the real SIF ingest path (idempotent upsert).
        # This is the FALLBACK catalog; real HM products (below) take precedence where mapped.
        catalog_sif = SYNTHETIC / "dealer_catalog.sif"
        if catalog_sif.exists():
            sif = parse_sif(catalog_sif.read_text())
            result = service.upsert_catalog(db, sif, source="sif")
            print(f"[bootstrap] catalog: +{result.created} new, {result.updated} updated, "
                  f"{result.matched} matched")

        # Load REAL Herman Miller products from the published price-book PDFs (source=pricebook)
        # so the studio quote prices HM items off real list prices, not the synthetic seed.
        report = ingest_hm_pricebooks(db)
        for r in report:
            if r["parsed"]:
                print(f"[bootstrap] pricebook {r['file']} ({r['note']}): "
                      f"{r['parsed']} real product(s): {r['skus']}")
            elif r.get("present"):
                print(f"[bootstrap] pricebook {r['file']} ({r['note']}): 0 parsed (skipped, "
                      f"does not match Step-N grammar)")

        # Apply the REAL NASPO/WA-DES MillerKnoll co-op discount band for HMI (0.505) so the
        # quote nets HM list at the real cooperative discount.
        apply_coop_hmi_band(db)

        # Studio pillars: synthetic procurement vendors + illustrative WELL/sustainability certs.
        seed_vendors(db)   # synthetic US vendors for RFQ/PO (real dealer terms are private)
        seed_certs(db)     # illustrative WELL/EPD certs for catalog SKUs (placeholder data)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap()
    yield


app = FastAPI(
    title="DSource — Dealer-facing Commercial Interiors Quoting (Phase 0)",
    version="0.2.0",
    description="SIF/pCon ingest → normalized catalog → budgetary quote. Single-tenant pilot spine.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(ingest.router)
app.include_router(quote.router)
app.include_router(projects.router)
app.include_router(gsa.router)    # real-data connector: GSA Advantage furniture price lists
app.include_router(coop.router)   # real-data connector: cooperative-contract discount bands
app.include_router(floorplan.router)  # Phase 1: vector floor-plate ingestion + capacity
app.include_router(testfit.router)    # Phase 2: generative test-fit (workstation field)
app.include_router(alternatives.router)  # Qbiq: 3 test-fit alternatives + space metrics
app.include_router(generate.router)      # Qbiq Concept: program + plate -> generated test-fit versions
app.include_router(generate_detailed.router)  # Qbiq Detailed: explicit room counts + placement -> versions
app.include_router(version_export.router)     # export a selected generated version (takeoff/IFC from its fit)
app.include_router(takeoff.router)       # Qbiq: quantity-takeoff Excel (BOM) export
app.include_router(report.router)        # Qbiq: styled multi-page space-planning PDF report
app.include_router(ifc.router)           # Qbiq: IFC4/BIM export (open-standard editable model)
app.include_router(floorplan_raster.router)  # Qbiq: raster/PDF floor-plate ingest (JPG/PNG/PDF)
app.include_router(ingest_cad.router)        # Ingestion: read a CAD layout -> real ExtractedLayout
app.include_router(ingest_raster.router)     # Ingestion: read a raster/PDF layout -> ExtractedLayout
app.include_router(layout_takeoff.router)    # Qbiq takeoff: ExtractedLayout -> multi-sheet xlsx
app.include_router(library.router)           # Steelcase catalog: settings (rooms) + products (SKUs) for slotting/swap
app.include_router(render.router)     # AI photoreal render proxy (needs provider key)
app.include_router(brief.router)       # Studio: HQ brief → program spec translation
app.include_router(wellcatalog.router) # Studio: WELL-ranked catalog
app.include_router(procurement.router) # Studio: smart procurement (RFQ → PO)
app.include_router(cad.router)         # CAD viewer: faithful 2D SVG + 3D geometry of the drawing
app.include_router(match.router)       # DSource AI: catalog match (text/image -> real products)
app.include_router(source.router)      # DSource AI: test-fit -> real India SKUs (INR sourcing)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "dsource", "phase": 0, "db": settings.database_url.split("://")[0]}
