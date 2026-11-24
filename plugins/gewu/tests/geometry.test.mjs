import test from 'node:test';
import assert from 'node:assert/strict';
import {mmToScreen, screenToMM, boxToScreen, rectFromPoints, roundMM, nudgeStep,
        fitScale, intersects, boundingBox} from '../web/geometry.mjs';

const view = {scale: 2, panX: 10, panY: 20};

test('mm and screen coordinates round-trip', () => {
  for (const point of [{x: 0, y: 0}, {x: 12.5, y: 3.25}, {x: -4, y: 60}]) {
    const back = screenToMM(mmToScreen(point, view), view);
    assert.ok(Math.abs(back.x - point.x) < 1e-9);
    assert.ok(Math.abs(back.y - point.y) < 1e-9);
  }
});

test('boxes keep the figure origin at the pan offset', () => {
  assert.deepEqual(boxToScreen([4, 6, 50, 20], view), {x: 18, y: 32, w: 100, h: 40});
});

test('dragging to the left and up still gives a positive box', () => {
  assert.deepEqual(rectFromPoints({x: 10, y: 8}, {x: 2, y: 3}), [2, 3, 8, 5]);
});

test('written geometry keeps two decimals', () => {
  assert.equal(roundMM(1 / 3), 0.33);
  assert.equal(roundMM(-1.005), -1);
});

test('nudge steps follow Fignimble: 0.5 mm, shift 5, alt 0.1', () => {
  assert.equal(nudgeStep(false, false), 0.5);
  assert.equal(nudgeStep(true, false), 5);
  assert.equal(nudgeStep(false, true), 0.1);
});

test('fit keeps both dimensions inside the viewport', () => {
  const scale = fitScale([120, 60], {w: 600, h: 400});
  assert.ok(120 * scale <= 600 - 47);
  assert.ok(60 * scale <= 400 - 47);
});

test('marquee hit testing and the selection box', () => {
  assert.equal(intersects([0, 0, 10, 10], [5, 5, 10, 10]), true);
  assert.equal(intersects([0, 0, 4, 4], [5, 5, 10, 10]), false);
  assert.deepEqual(boundingBox([[0, 0, 10, 5], [20, 4, 5, 10]]), [0, 0, 25, 14]);
});
