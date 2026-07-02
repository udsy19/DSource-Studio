// Pure gesture math for the scene editor's on-canvas rotate grip — extracted so the regression that
// bit us (a bare grip click doing nothing) is locked by a fast unit test, independent of the DOM.

// A bare click on the grip (no drag) rotates by this much — a Canva idiom.
export const CLICK_ROTATE_DEG = 90;

// The backend snaps every rotation to 45° (_snap_45); the live preview snaps to the same grid so a
// small drag visibly clicks to the next detent instead of silently rounding home.
export const snap45 = (deg: number) => (((Math.round(deg / 45) * 45) % 360) + 360) % 360;

// Normalize a rotation delta to (-180, 180] so a grip-drag sends the short way round.
export const normalizeDelta = (deg: number) => {
  const x = ((deg % 360) + 360) % 360;
  return x > 180 ? x - 360 : x;
};

// The rotation delta a completed grip gesture commits, or null for a no-op. THE REGRESSION GUARD: a
// bare click (moved === false) must rotate +90° — it used to fall through the pointer-up guard and
// do nothing. A drag commits its (already 45°-snapped) delta unless it returned to the same detent.
export function rotateGestureCommand(
  moved: boolean,
  previewDeg: number | null,
  currentRotation: number,
): number | null {
  if (!moved) return CLICK_ROTATE_DEG;
  if (previewDeg === null) return null;
  const delta = normalizeDelta(previewDeg - currentRotation);
  return delta !== 0 ? delta : null;
}
