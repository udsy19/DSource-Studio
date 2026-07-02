"""AI photoreal render scaffold.

Captures a 3D-view image from the studio and forwards it to a configured external
image-to-image API (Decor8 / Spacely / HomeDesignsAI / etc.) to return a photoreal render.

HONEST: this is a thin, provider-agnostic proxy. It does NOT generate anything itself — it
needs `RENDER_API_URL` + `RENDER_API_KEY` set in the environment (the user's paid provider).
Unconfigured, it returns a clear 501 so the UI can prompt for a key rather than fake a render.
The request shape below is the common "image + prompt -> image" pattern; the response adapter
is intentionally permissive (most providers return an image URL or base64) and may need a
one-line tweak per provider.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings

router = APIRouter(prefix="/api/render", tags=["render"])


_BASE_PROMPT = (
    "photorealistic modern commercial office interior, same furniture layout, "
    "soft natural daylight, architectural photography"
)

# Visualization finishes → the phrase folded into the render prompt. Order gives a natural sentence.
_FINISH_PHRASES: list[tuple[str, str]] = [
    ("wall", "{} walls"),
    ("floor", "{} floor"),
    ("partition", "{} partitions"),
    ("palette", "{} palette"),
    ("style", "{} style"),
]


def build_render_prompt(finishes: dict[str, str]) -> str:
    """Compose the image-to-image prompt from the user's finish selections, always keeping the
    layout-preserving base (the render must not reinvent the furniture arrangement). Blank/omitted
    finishes are skipped, so an empty selection returns the base prompt unchanged."""
    parts = [_BASE_PROMPT]
    for key, template in _FINISH_PHRASES:
        value = (finishes.get(key) or "").strip()
        if value:
            parts.append(template.format(value))
    return ", ".join(parts)


# Per-surface edit instructions for the Kontext targeted-edit model. Each names ONE surface/finish
# and pins the rest — Kontext changes only what the prompt describes, so the AI beauty layer never
# moves the structured layout. Distinct from build_render_prompt (which seeds the full-scene render).
_EDIT_TEMPLATES: dict[str, str] = {
    "wall": "Change the walls to {}",
    "floor": "Change the floor to {}",
    "partition": "Change the partitions to {}",
    "palette": "Shift the overall colour palette to {}",
    "style": "Restyle the space in a {} style",
}
_EDIT_KEEP = ". Keep the exact same room layout, furniture, camera angle and everything else unchanged."


def build_edit_instruction(field: str, value: str, scope: str | None = None) -> str:
    """Compose a targeted, layout-preserving edit instruction for one finish selection. Raises 422
    on a blank value or an unknown field so we never send the model an empty/ambiguous edit.

    `scope` optionally confines the change to one room/space (e.g. "meeting room"): the surface
    phrase gains an "in the <scope>" locator so Kontext edits only that room and leaves the rest
    identical. A blank/omitted scope keeps the current global wording (back-compatible)."""
    value = (value or "").strip()
    if not value:
        raise HTTPException(status_code=422, detail="An edit needs a non-empty finish value.")
    template = _EDIT_TEMPLATES.get(field)
    if not template:
        raise HTTPException(status_code=422, detail=f"Unknown finish field: {field}")
    locator = f" in the {scope.strip()}" if (scope or "").strip() else ""
    return template.format(value) + locator + _EDIT_KEEP


class RenderRequest(BaseModel):
    image: str  # data URL or base64 PNG/JPEG of the 3D view
    prompt: str = _BASE_PROMPT
    finishes: dict[str, str] | None = None  # when set, the prompt is composed from these selections


class RenderEditRequest(BaseModel):
    image: str  # the CURRENT render (data URL) to edit in place
    field: str  # which finish surface to change (wall / floor / partition / palette / style)
    value: str  # the new finish, e.g. "walnut wood panel"
    scope: str | None = None  # optional room/space to confine the edit to, e.g. "meeting room"


@router.get("/status")
def status():
    has_key = bool(settings.replicate_api_token if settings.render_provider == "replicate" else settings.render_api_key)
    return {
        "configured": has_key,
        "provider": settings.render_provider,
        "model": settings.render_model or None,
        # Targeted per-surface edits run on the Kontext model (Replicate-only), regardless of the
        # base render provider — so the UI gates the surface-refine controls on this separately.
        "edit_configured": bool(settings.replicate_api_token),
        "edit_model": settings.render_edit_model or None,
    }


def _strip_data_url(image: str) -> str:
    return image.split(",", 1)[1] if image.startswith("data:") else image


async def _render_gemini(image_b64: str, prompt: str) -> str:
    """Nano Banana — Gemini 2.5 Flash Image. Image-to-image: the 3D view + a text instruction."""
    model = settings.render_model or "gemini-2.5-flash-image"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {"parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
            ]}
        ]
    }
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, params={"key": settings.render_api_key}, json=payload)
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Gemini error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inline_data") or part.get("inlineData")
            if inline and inline.get("data"):
                mime = inline.get("mime_type") or inline.get("mimeType") or "image/png"
                return f"data:{mime};base64,{inline['data']}"
    raise HTTPException(status_code=502, detail="Gemini returned no image (check the model + prompt).")


async def _render_generic(image: str, prompt: str) -> str:
    if not settings.render_api_url:
        raise HTTPException(status_code=501, detail="provider=generic needs RENDER_API_URL in .env.")
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            settings.render_api_url,
            headers={"Authorization": f"Bearer {settings.render_api_key}"},
            json={"image": image, "prompt": prompt, "model": settings.render_model},
        )
    resp.raise_for_status()
    data = resp.json()
    img = data.get("image") or data.get("output") or data.get("url") or (data.get("images") or [None])[0]
    if not img:
        raise HTTPException(status_code=502, detail="Provider returned no image.")
    return img


async def _replicate_run(model: str, inp: dict) -> str:
    """POST a Replicate prediction and poll to completion, returning the output image URL/data.
    Shared by the ControlNet full-scene render and the Kontext targeted edit."""
    token = settings.replicate_api_token
    url = f"https://api.replicate.com/v1/models/{model}/predictions"
    headers = {"Authorization": f"Bearer {token}", "Prefer": "wait", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=200) as client:
        resp = await client.post(url, headers=headers, json={"input": inp})
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Replicate error {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        get_url = (data.get("urls") or {}).get("get")
        for _ in range(50):  # poll up to ~100s if Prefer:wait didn't finish
            st = data.get("status")
            if st == "succeeded":
                break
            if st in ("failed", "canceled"):
                raise HTTPException(status_code=502, detail=f"Replicate {st}: {data.get('error')}")
            if not get_url:
                break
            await asyncio.sleep(2)
            data = (await client.get(get_url, headers={"Authorization": f"Bearer {token}"})).json()
    out = data.get("output")
    if isinstance(out, list):
        out = out[0] if out else None
    if not out:
        raise HTTPException(status_code=502, detail="Replicate returned no image.")
    return out


async def _render_replicate(image_data_url: str, prompt: str) -> str:
    """ControlNet interior model on Replicate — conditions on the 3D view's STRUCTURE so the
    photoreal output keeps the exact room layout (vs Gemini, which reinterprets freely)."""
    model = settings.render_model if "/" in (settings.render_model or "") else "black-forest-labs/flux-canny-dev"
    if "flux" in model:  # Flux ControlNet: edges of the control image bind the output -> layout preserved
        inp = {"control_image": image_data_url, "prompt": prompt, "guidance": 30,
               "num_inference_steps": 32, "megapixels": "1", "output_format": "jpg",
               "output_quality": 92}
    else:               # generic ControlNet (image + prompt_strength)
        inp = {"image": image_data_url, "prompt": prompt, "prompt_strength": 0.72,
               "num_inference_steps": 30, "guidance_scale": 12}
    return await _replicate_run(model, inp)


def build_kontext_input(image_data_url: str, instruction: str) -> dict:
    """The flux-kontext-pro prediction input, per its published OpenAPI schema. `input_image` accepts
    a base64 data URI as well as a hosted URL. aspect_ratio is omitted so it defaults to
    match_input_image (the layout must not be reframed); safety_tolerance is pinned at 2, the model's
    documented maximum whenever an input image is supplied."""
    return {"prompt": instruction, "input_image": image_data_url,
            "output_format": "jpg", "safety_tolerance": 2}


async def _render_kontext(image_data_url: str, instruction: str) -> str:
    """flux-kontext-pro — a TARGETED edit: changes only what `instruction` names, leaving the rest
    of the render intact. This is the per-surface finish swap, distinct from the full-scene render."""
    return await _replicate_run(settings.render_edit_model, build_kontext_input(image_data_url, instruction))


@router.post("")
async def render(req: RenderRequest):
    prompt = build_render_prompt(req.finishes) if req.finishes else req.prompt
    provider = (settings.render_provider or "gemini").lower()
    if provider == "replicate":
        if not settings.replicate_api_token:
            raise HTTPException(status_code=501, detail="Set REPLICATE_API_TOKEN in backend/.env.")
        return {"image": await _render_replicate(req.image, prompt)}
    if provider == "gemini":
        if not settings.render_api_key:
            raise HTTPException(status_code=501, detail="Set RENDER_API_KEY (Gemini) in backend/.env.")
        return {"image": await _render_gemini(_strip_data_url(req.image), prompt)}
    return {"image": await _render_generic(req.image, prompt)}


@router.post("/edit")
async def render_edit(req: RenderEditRequest):
    """Targeted per-surface finish swap via the Kontext model — edits ONLY the named surface on an
    existing render, leaving the layout and everything else intact. Replicate-only, so it gates on
    REPLICATE_API_TOKEN regardless of the base render provider."""
    if not settings.replicate_api_token:
        raise HTTPException(status_code=501, detail="Targeted edits need REPLICATE_API_TOKEN in backend/.env.")
    instruction = build_edit_instruction(req.field, req.value, req.scope)
    return {"image": await _render_kontext(req.image, instruction)}
