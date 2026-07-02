"""Scene metrics — a PURE function of the scene, recomputed after every command.

Reuses the existing live-layout metric logic (`ingestion.layout_metrics.compute_layout_metrics`)
rather than reinventing seats/areas/density: the scene is projected to an `ExtractedLayout` view and
scored, then a program scoreboard (actual vs target per room type) is laid on top against
`scene.program_ref`. Nothing is invented — every number derives from the scene geometry.
"""

from __future__ import annotations

from collections import Counter

from ..ingestion.layout_metrics import compute_layout_metrics
from .geometry import scene_to_layout
from .model import Scene


def _program_scoreboard(scene: Scene) -> dict:
    """Actual zone counts per room type vs the program targets — the editor's scoreboard."""
    actual = Counter(z.room_type for z in scene.zones)
    lines = [
        {"room_type": line.room_type, "label": line.label,
         "target": line.target, "actual": actual.get(line.room_type, 0)}
        for line in scene.program_ref.lines
    ]
    return {
        "headcount": scene.program_ref.headcount,
        "density_rsf_per_person": scene.program_ref.density_rsf_per_person,
        "lines": lines,
    }


def compute_scene_metrics(scene: Scene) -> dict:
    """Seats, areas, density and room mix (from compute_layout_metrics) + the program scoreboard."""
    metrics = compute_layout_metrics(scene_to_layout(scene))
    metrics["program"] = _program_scoreboard(scene)
    return metrics
