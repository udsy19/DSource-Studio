import { describe, it, expect } from "vitest";
import { normalizeDelta, rotateGestureCommand, snap45 } from "./sceneGestures";

describe("rotateGestureCommand", () => {
  // THE regression: a bare grip click (no drag) used to fall through and do nothing.
  it("rotates +90 on a bare click (no drag)", () => {
    expect(rotateGestureCommand(false, null, 0)).toBe(90);
    expect(rotateGestureCommand(false, null, 45)).toBe(90); // independent of current rotation
  });

  it("commits the drag delta when the grip moved to a new detent", () => {
    expect(rotateGestureCommand(true, 90, 0)).toBe(90);
    expect(rotateGestureCommand(true, 135, 45)).toBe(90);
  });

  it("is a no-op when a drag returned to the same detent", () => {
    expect(rotateGestureCommand(true, 45, 45)).toBeNull();
    expect(rotateGestureCommand(true, null, 0)).toBeNull(); // moved flag set but no preview captured
  });

  it("sends the short way round (normalized to (-180,180])", () => {
    expect(rotateGestureCommand(true, 315, 0)).toBe(-45); // not +315
  });
});

describe("snap45", () => {
  it("snaps to the nearest 45° and wraps into [0,360)", () => {
    expect(snap45(30)).toBe(45); // 30 is nearer 45 than 0
    expect(snap45(20)).toBe(0); //  20 is nearer 0 than 45
    expect(snap45(-10)).toBe(0);
    expect(snap45(370)).toBe(0);
  });
});

describe("normalizeDelta", () => {
  it("maps to (-180, 180]", () => {
    expect(normalizeDelta(270)).toBe(-90);
    expect(normalizeDelta(-270)).toBe(90);
    expect(normalizeDelta(180)).toBe(180);
  });
});
