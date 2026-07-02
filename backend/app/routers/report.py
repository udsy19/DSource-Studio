"""Report router — render the styled multi-page "Space Planning Report" PDF.

`POST /api/testfit/report` takes a fully-formed `ReportData` body (project + plan + the three
alternatives, each with its test-fit geometry and metrics) and streams back a PDF. It does no
computation of its own: the caller assembles the data; this endpoint only renders it.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..report.service import build_report_pdf

router = APIRouter(prefix="/api/testfit", tags=["report"])


class Project(BaseModel):
    client: str
    building: str
    style: str
    floor: str


class Plan(BaseModel):
    boundary: list[list[float]]
    cores: list[list[list[float]]] = Field(default_factory=list)
    columns: list[list[float]] = Field(default_factory=list)
    gross_area_sf: float
    usable_area_sf: float
    units: str


class Instance(BaseModel):
    type: str
    x: float
    y: float
    w: float
    h: float
    rotation: int = 0


class TestFit(BaseModel):
    instances: list[Instance] = Field(default_factory=list)


class Metrics(BaseModel):
    usf: float
    seats: int
    open_space_seats: int
    offices: int
    conf_rooms: int
    density_sf_per_person: float
    daylight_pct: float
    privacy_pct: float
    efficiency_pct: float


class Alternative(BaseModel):
    id: str
    testfit: TestFit
    metrics: Metrics


class ReportData(BaseModel):
    project: Project
    plan: Plan
    alternatives: list[Alternative]
    render_image: str | None = None  # data-URL or bare base64 of the photoreal render, when present
    qr_url: str | None = None  # honest link the cover QR points to (e.g. this project in DSource)


@router.post("/report")
def generate_report(data: ReportData) -> StreamingResponse:
    pdf = build_report_pdf(data.model_dump())
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="space-planning-report.pdf"'},
    )
