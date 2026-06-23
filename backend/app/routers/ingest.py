from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingest import service
from ..ingest.pcon_excel import parse_pcon
from ..ingest.sif import parse_sif
from ..pricebook.parser import parse_book
from ..schemas import IngestReport, PriceBookReport

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/catalog", response_model=IngestReport)
async def ingest_catalog(
    file: UploadFile = File(...),
    format: str = Form("sif"),  # sif | pcon
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    mapping = None
    if format == "pcon":
        sif, mapping = parse_pcon(content, file.filename or "upload")
    else:
        sif = parse_sif(content.decode("utf-8", errors="replace"))
    result = service.upsert_catalog(db, sif, source=format)
    return IngestReport(
        kind="catalog", source=format, title=result.title, items_read=result.items_read,
        created=result.created, updated=result.updated, matched=result.matched,
        column_mapping=mapping, warnings=result.warnings,
    )


@router.post("/project", response_model=IngestReport)
async def ingest_project(
    file: UploadFile = File(...),
    name: str = Form("Imported Project"),
    format: str = Form("sif"),
    db: Session = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    mapping = None
    if format == "pcon":
        sif, mapping = parse_pcon(content, file.filename or "upload")
    else:
        sif = parse_sif(content.decode("utf-8", errors="replace"))
    project = service.build_project(db, sif, name=name or sif.title or "Imported Project", source=format)
    return IngestReport(
        kind="project", source=format, title=sif.title, items_read=len(sif.items),
        project_id=project.id, column_mapping=mapping, warnings=sif.warnings,
    )


@router.post("/pricebook", response_model=PriceBookReport)
async def ingest_pricebook(
    file: UploadFile = File(...),
    manufacturer_code: str = Form(...),
    db: Session = Depends(get_db),
):
    """Parse a manufacturer price-book PDF (a configurator) into real catalog products.

    Each base model is loaded at its 'starting configuration' list price — a real part
    number + real list price sourced from the manufacturer's published price book.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Expected a .pdf price book.")
    try:
        book = parse_book(content)
    except Exception as exc:  # noqa: BLE001 - surface parse errors
        raise HTTPException(status_code=422, detail=f"Could not parse PDF: {exc}") from exc

    results, warnings = service.upsert_price_book(db, book, manufacturer_code=manufacturer_code)
    return PriceBookReport(
        title=book.title, manufacturer_code=manufacturer_code,
        products_parsed=len(book.products),
        products=[vars(r) for r in results], warnings=warnings,
    )
