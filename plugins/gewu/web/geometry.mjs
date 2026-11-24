// Millimetre geometry: the figure's top-left is (0,0), y grows down, units are mm.
export function mmToScreen(point, view) {
  return {x: view.panX + point.x * view.scale, y: view.panY + point.y * view.scale};
}

export function screenToMM(point, view) {
  return {x: (point.x - view.panX) / view.scale, y: (point.y - view.panY) / view.scale};
}

export function boxToScreen(box, view) {
  const [x, y, w, h] = box;
  return {x: view.panX + x * view.scale, y: view.panY + y * view.scale,
          w: w * view.scale, h: h * view.scale};
}

export function rectFromPoints(a, b) {
  return [Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(a.x - b.x), Math.abs(a.y - b.y)];
}

export function roundMM(value) {
  return Math.round(value * 100) / 100;
}

export function nudgeStep(shift, alt) {
  if (alt) return 0.1;
  return shift ? 5 : 0.5;
}

export function fitScale(size, viewport, margin = 24) {
  const [w, h] = size;
  const scale = Math.min((viewport.w - margin * 2) / w, (viewport.h - margin * 2) / h);
  return Math.max(0.2, Math.min(40, scale));
}

export function intersects(a, b) {
  const [ax, ay, aw, ah] = a;
  const [bx, by, bw, bh] = b;
  return ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah;
}

export function boundingBox(boxes) {
  const xs = boxes.map((b) => b[0]);
  const ys = boxes.map((b) => b[1]);
  const rights = boxes.map((b) => b[0] + b[2]);
  const bottoms = boxes.map((b) => b[1] + b[3]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...rights) - Math.min(...xs),
          Math.max(...bottoms) - Math.min(...ys)];
}
