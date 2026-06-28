"""Export a SELECTED generated version directly — takeoff (Excel) and BIM (IFC) from the version's
plan + test-fit, so "generate -> pick a version -> download its deliverables" is one coherent loop
(no re-running generation). The PDF report already accepts the generated plan+alternatives via
/api/testfit/report.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..ifc.service import build_ifc
from ..takeoff.service import build_takeoff_workbook
from ..testfit.dxf_export import build_testfit_dxf
from ..testfit.payloads import fit_from_payload, plan_from_payload

router = APIRouter(prefix="/api/testfit", tags=["version-export"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class FitExport(BaseModel):
    plan: dict  # a plan_payload
    testfit: dict  # a testfit_payload (the selected version's fit)


@router.post("/takeoff-from-fit")
def takeoff_from_fit(req: FitExport, db: Session = Depends(get_db)):
    wb = build_takeoff_workbook(db, plan_from_payload(req.plan), fit_from_payload(req.testfit))
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="quantity-takeoff.xlsx"'},
    )


@router.post("/ifc-from-fit")
def ifc_from_fit(req: FitExport):
    data = build_ifc(plan_from_payload(req.plan), fit_from_payload(req.testfit))
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-step",
        headers={"Content-Disposition": 'attachment; filename="model.ifc"'},
    )


@router.post("/dxf-from-fit")
def dxf_from_fit(req: FitExport):
    data = build_testfit_dxf(plan_from_payload(req.plan), fit_from_payload(req.testfit))
    return StreamingResponse(
        io.BytesIO(data),
        media_type="image/vnd.dxf",
        headers={"Content-Disposition": 'attachment; filename="test-fit.dxf"'},
    )
