// jsdom lacks Pointer Capture; the scene editor's drag/rotate handlers call it. Stub to no-ops so
// component tests can dispatch pointer events without throwing.
if (!Element.prototype.setPointerCapture) Element.prototype.setPointerCapture = () => {};
if (!Element.prototype.releasePointerCapture) Element.prototype.releasePointerCapture = () => {};
if (!Element.prototype.hasPointerCapture) Element.prototype.hasPointerCapture = () => false;
