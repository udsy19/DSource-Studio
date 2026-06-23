from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingest import service
from ..models import DealerSettings, Product, Project
from ..schemas import DealerSettingsOut, ProjectOut

router = APIRouter(prefix="/api", tags=["projects"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id.desc()).all()


@router.get("/projects/{project_id}/lines")
def project_lines(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    out = []
    for line in project.lines:
        product = db.get(Product, line.product_id)
        out.append({
            "product_id": line.product_id,
            "manufacturer_code": product.manufacturer_code if product else None,
            "sku": product.sku if product else None,
            "name": product.name if product else None,
            "qty": line.qty,
            "list_price": line.list_price_override or (product.list_price if product else 0),
            "discount_override": line.discount_override,
        })
    return {"project_id": project_id, "name": project.name, "lines": out}


@router.get("/settings", response_model=DealerSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return service.get_settings(db)
