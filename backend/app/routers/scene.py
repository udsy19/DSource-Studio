"""Scene editor API — the HTTP boundary over the semantic scene model.

Stateless by design: the browser holds the scene JSON and its own undo/redo history of snapshots;
each `apply` runs ONE command server-side (validated + rolled back on any invariant violation) and
returns the new scene + recomputed metrics. The plate picker is the existing /api/library/settings
(a plate id IS a setting id); swap/merge/enclose commands send only that id, resolved here.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..scene.adapters import scene_from_generated
from ..scene.commands import CommandStack
from ..scene.export import scene_to_dxf
from ..scene.metrics import compute_scene_metrics
from ..scene.model import SceneError
from ..scene.plates import resolve_plate
from ..scene.serialize import build_command, scene_from_dict, scene_to_dict
from ..testfit.payloads import fit_from_payload, plan_from_payload

router = APIRouter(prefix="/api/scene", tags=["scene"])


class FromFitRequest(BaseModel):
    plan: dict
    testfit: dict
    program: dict | None = None


class SceneRequest(BaseModel):
    scene: dict


class ApplyRequest(BaseModel):
    scene: dict
    command: dict  # {type, ...args}; plate-taking commands carry a plate_id resolved server-side


def _scene_response(scene) -> dict:
    return {"scene": scene_to_dict(scene), "metrics": compute_scene_metrics(scene)}


@router.post("/from-fit")
def from_fit(req: FromFitRequest):
    """Build an editable scene from a generated test-fit (plan + testfit + optional program) — the
    bridge from the generate flow into the editor. The base building becomes the locked underlay."""
    try:
        plan = plan_from_payload(req.plan)
        instances = fit_from_payload(req.testfit).instances
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Malformed plan/testfit payload: {exc}") from exc
    scene = scene_from_generated(plan, instances, req.program)
    return _scene_response(scene)


@router.post("/apply")
def apply(req: ApplyRequest):
    """Apply one command to the scene. A command that would break an invariant is rejected (422 with
    a code+message) and the scene is unchanged — the client keeps its prior snapshot."""
    scene = scene_from_dict(req.scene)
    try:
        command = build_command(req.command, resolve_plate)
        CommandStack(scene).execute(command)
    except SceneError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    return _scene_response(scene)


@router.post("/metrics")
def metrics(req: SceneRequest):
    """Recompute the scoreboard for a scene (seats/areas/density + actual-vs-target per program line)."""
    return compute_scene_metrics(scene_from_dict(req.scene))


@router.post("/dxf")
def dxf(req: SceneRequest):
    """Compile the current scene to a DXF (underlay passthrough + generated design on our layers) —
    the on-demand `scene → dxf` export, invokable anytime per edited design."""
    data = scene_to_dxf(scene_from_dict(req.scene))
    return StreamingResponse(
        io.BytesIO(data),
        media_type="image/vnd.dxf",
        headers={"Content-Disposition": "attachment; filename=design.dxf"},
    )
