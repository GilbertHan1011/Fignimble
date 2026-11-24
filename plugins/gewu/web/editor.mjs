// Fignimble in GeWu: the figure is Python, the canvas is a second client of the
// engine, and every gesture is one native edit. Geometry is mm, y down.
import {connect, invoke, resourceUrl, publishContext, saveState, saved} from './bridge.mjs';
import {screenToMM, boxToScreen, rectFromPoints, roundMM, nudgeStep, fitScale,
        intersects, boundingBox} from './geometry.mjs';

const el = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

const state = {
  figure: null, scene: null, revision: null, snapshotId: null, fileRevision: null,
  selection: [], scale: 6, panX: 18, panY: 18, dark: false, tool: 'select',
  version: -1, drag: null, sourceDirty: false, busy: false, pane: 'code', thumbs: new Map(),
  manualZoom: false, fitValidated: false,
};
const nodes = new Map();
const urls = new Map();

function toast(message, error = false) {
  const node = el('toast');
  node.textContent = message;
  node.classList.toggle('error', error);
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, error ? 9000 : 2600);
}

function setStatus(text, error = false) {
  el('status').textContent = text;
  el('status').classList.toggle('error', error);
}

async function run(fn, what = 'That action') {
  if (state.busy) { toast('Still working on the last action…'); renderScene(); return; }
  state.busy = true;
  try {
    await fn();
  } catch (error) {
    setStatus(`${what} failed: ${error.message}`, true);
    toast(`${what} failed: ${error.message}`, true);
    if (state.scene) { drawOverlay(); renderInspector(); }
  } finally {
    state.busy = false;
  }
}

function urlFor(ref) {
  const key = `${ref.uri}@${ref.revision ?? ''}`;
  if (!urls.has(key)) urls.set(key, resourceUrl(ref));
  return urls.get(key);
}

// --- figures and scene -------------------------------------------------------

async function refreshFigures() {
  const result = await invoke('state', {limit: 200});
  const data = result.data;
  state.revision = data.revision;
  const list = el('figures');
  list.replaceChildren();
  for (const figure of data.figures) {
    const card = document.createElement('li');
    card.className = 'figure-card';
    card.dataset.figure = figure.name;
    card.setAttribute('aria-current', String(figure.name === state.figure));
    const img = document.createElement('img');
    img.className = 'thumb' + (figure.thumb ? '' : ' empty');
    img.alt = figure.name;
    if (figure.thumb) urlFor(figure.thumb).then((url) => { img.src = url; }).catch(() => { img.classList.add('empty'); });
    card.append(img);
    const caption = document.createElement('div');
    caption.className = 'caption';
    const name = document.createElement('span');
    name.textContent = figure.name;
    caption.append(name);
    const count = figure.warnings ?? 0;
    if (figure.error) {
      const badge = document.createElement('span'); badge.className = 'badge error'; badge.textContent = 'error';
      caption.append(badge); card.title = figure.error;
    } else if (count) {
      const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = `${count} warning${count > 1 ? 's' : ''}`;
      caption.append(badge);
    }
    card.append(caption);
    card.addEventListener('click', () => run(() => openFigure(figure.name), `Open ${figure.name}`));
    list.append(card);
  }
  setStatus(`${data.project} · ${data.figures.length} figure(s)`);
}

async function openFigure(name, options = {}) {
  const result = await invoke('figure', {figure: name, pxPerMM: 12});
  state.figure = name;
  await applyPayload(result.data, options);
  if (options.restore && saved.snapshotId === state.snapshotId) {
    state.selection = [...(saved.selection ?? [])];
  } else {
    state.selection = [];
  }
  state.zoomChosen = false;
  state.manualZoom = false;
  state.fitDone = false;
  await refreshFigures();
  await retargetSource();
  const initialScale = state.scale;
  fitIfNeeded();
  ensureFits();
  if (Math.abs(state.scale - initialScale) > 0.001) renderScene();
  drawOverlay();
  report();
  fitWhenLaidOut();
}

async function applyPayload(data, options = {}) {
  if (data.revision) state.revision = data.revision;
  if (data.snapshotId) state.snapshotId = data.snapshotId;
  if (typeof data.dark === 'boolean') state.dark = data.dark;
  if (data.scene) await loadScene(data.scene, options);
}

async function loadScene(ref, options = {}) {
  const url = await urlFor(ref);
  const response = await fetch(url, {credentials: 'omit'});
  if (!response.ok) throw Error(`Could not read the preview scene (${response.status})`);
  state.scene = await response.json();
  if (!options.keepSelection) {
    const known = new Set(allElements().map((item) => item.oid));
    state.selection = state.selection.filter((oid) => known.has(oid));
  }
  renderScene();
}

function allElements() {
  return [...(state.scene?.elements ?? []), ...(state.scene?.labels ?? [])];
}

function byOid(oid) {
  return allElements().find((item) => item.oid === oid) ?? null;
}

function renderScene() {
  const figure = el('figure');
  const scene = state.scene;
  if (!scene) return;
  const [w, h] = scene.size;
  const scale = state.scale;
  figure.style.left = `${state.panX}px`;
  figure.style.top = `${state.panY}px`;
  figure.style.width = `${w * scale}px`;
  figure.style.height = `${h * scale}px`;
  figure.style.background = scene.background || '#ffffff';
  figure.replaceChildren();
  nodes.clear();
  for (const item of scene.elements) {
    if (item.sprite) {
      const sprite = item.sprite;
      const img = document.createElement('img');
      img.className = 'sprite';
      img.alt = '';
      img.style.left = `${sprite.x * scale}px`;
      img.style.top = `${sprite.y * scale}px`;
      img.style.width = `${sprite.w * scale}px`;
      img.style.height = `${sprite.h * scale}px`;
      figure.append(img);
      urlFor(sprite).then((url) => { img.src = url; }).catch(() => {});
      item.image = img;
    }
    if (item.box) {
      const hit = document.createElement('div');
      hit.className = 'hit';
      hit.dataset.oid = item.oid;
      hit.style.left = `${item.box[0] * scale}px`;
      hit.style.top = `${item.box[1] * scale}px`;
      hit.style.width = `${item.box[2] * scale}px`;
      hit.style.height = `${item.box[3] * scale}px`;
      hit.title = `${item.kind ?? 'element'} ${item.oid}`;
      figure.append(hit);
      nodes.set(item.oid, {img: item.image ?? null, hit});
    }
  }
  for (const label of scene.labels ?? []) {
    if (!label.sprite) continue;
    const sprite = label.sprite;
    const img = document.createElement('img');
    img.className = 'sprite';
    img.alt = label.text ?? '';
    img.style.left = `${sprite.x * scale}px`;
    img.style.top = `${sprite.y * scale}px`;
    img.style.width = `${sprite.w * scale}px`;
    img.style.height = `${sprite.h * scale}px`;
    figure.append(img);
    urlFor(sprite).then((url) => { img.src = url; }).catch(() => {});
    if (label.box) {
      const hit = document.createElement('div');
      hit.className = 'hit';
      hit.dataset.oid = label.oid;
      hit.style.left = `${label.box[0] * scale}px`;
      hit.style.top = `${label.box[1] * scale}px`;
      hit.style.width = `${label.box[2] * scale}px`;
      hit.style.height = `${label.box[3] * scale}px`;
      figure.append(hit);
      nodes.set(label.oid, {img, hit});
    }
  }
  el('stage').style.width = `${state.panX * 2 + w * scale}px`;
  el('stage').style.height = `${state.panY * 2 + h * scale}px`;
  drawOverlay();
  renderRulers();
  renderLayers();
  renderWarnings();
  renderInspector();
  el('figure-path').textContent = scene.file ?? '';
  const problems = (scene.warnings ?? []).filter((warning) => warning.level !== 'info').length;
  el('figure-meta').textContent = `${Math.round(w)} × ${Math.round(h)} mm${problems ? ` · ${problems} preflight warning${problems > 1 ? 's' : ''}` : ''}`;
  el('pf-count').textContent = problems ? String(problems) : '';
}

// The pane can still be unlaid-out when a view opens; fall back to the window
// size minus this editor's own columns so the first view is never oversized.
function viewportBox() {
  const box = el('scroll').getBoundingClientRect();
  if (box.width && box.height) return {w: box.width, h: box.height};
  return {w: Math.max(160, innerWidth - 190 - 230 - 34 - 32),
          h: Math.max(160, innerHeight - 44 - 22 - 24 - Math.round(innerHeight * 0.34) - 32)};
}

function fitIfNeeded() {
  if (!state.scene || state.zoomChosen) return;
  const box = viewportBox();
  state.scale = fitScale(state.scene.size, box);
  state.panX = 24;
  state.panY = 22;
}

function fitWhenLaidOut() {
  const attempt = () => {
    if (state.fitDone || !state.scene || state.drag) return;
    ensureFits();
    if (!state.fitDone) setTimeout(attempt, 400);
  };
  requestAnimationFrame(() => requestAnimationFrame(attempt));
  setTimeout(attempt, 600);
}

function ensureFits() {
  if (!state.scene) return false;
  const box = viewportBox();
  state.fitValidated = true;
  const before = state.scale;
  state.zoomChosen = false;
  state.manualZoom = false;
  fitIfNeeded();
  state.fitDone = true;
  if (Math.abs(state.scale - before) > 0.001) { renderScene(); return true; }
  return false;
}

new ResizeObserver(() => {
  if (!state.scene || state.drag) return;
  if (state.fitValidated && state.manualZoom) return;
  ensureFits();
}).observe(document.getElementById('scroll'));

// --- rulers -----------------------------------------------------------------

function renderRulers() {
  const scene = state.scene;
  if (!scene) return;
  const [w, h] = scene.size;
  const top = el('ruler-top'), left = el('ruler-left');
  top.replaceChildren(); left.replaceChildren();
  const step = state.scale >= 3 ? 20 : state.scale >= 1.5 ? 50 : 100;
  const originX = 16 + state.panX, originY = 16 + state.panY;
  for (let mm = 0; mm <= w + 0.01; mm += step) {
    const x = originX + mm * state.scale;
    const tick = document.createElement('div');
    tick.className = 'tick';
    tick.style.left = `${x}px`;
    const value = document.createElement('span');
    value.textContent = String(Math.round(mm));
    tick.append(value);
    top.append(tick);
  }
  for (let mm = 0; mm <= h + 0.01; mm += step) {
    const y = originY + mm * state.scale;
    const tick = document.createElement('div');
    tick.className = 'tick';
    tick.style.top = `${y}px`;
    const value = document.createElement('span');
    value.textContent = String(Math.round(mm));
    tick.append(value);
    left.append(tick);
  }
}

// --- overlay and selection --------------------------------------------------

function svg(tag, attrs) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

function drawOverlay() {
  const overlay = el('overlay');
  overlay.replaceChildren();
  const scene = state.scene;
  if (!scene) return;
  const [w, h] = scene.size;
  overlay.setAttribute('viewBox', `0 0 ${state.panX * 2 + w * state.scale} ${state.panY * 2 + h * state.scale}`);
  overlay.style.width = `${state.panX * 2 + w * state.scale}px`;
  overlay.style.height = `${state.panY * 2 + h * state.scale}px`;
  for (const oid of state.selection) {
    const item = byOid(oid);
    if (!item?.box) continue;
    overlay.append(svg('rect', {...boxToScreen(item.box, state), class: 'sel', 'vector-effect': 'non-scaling-stroke'}));
  }
  if (state.selection.length === 1) {
    const item = byOid(state.selection[0]);
    if (item?.box) {
      const box = boxToScreen(item.box, state);
      overlay.append(svg('rect', {x: box.x + box.w - 4, y: box.y + box.h - 4, width: 8, height: 8,
        class: 'handle', 'data-handle': 'se'}));
      for (const divider of item.dividers ?? []) {
        const line = divider.axis === 'col'
          ? {x1: state.panX + divider.at * state.scale, y1: state.panY + divider.from * state.scale,
             x2: state.panX + divider.at * state.scale, y2: state.panY + divider.to * state.scale}
          : {x1: state.panX + divider.from * state.scale, y1: state.panY + divider.at * state.scale,
             x2: state.panX + divider.to * state.scale, y2: state.panY + divider.at * state.scale};
        overlay.append(svg('line', {...line, class: 'divider', 'data-divider': String(item.dividers.indexOf(divider))}));
      }
    }
  }
  if (state.drag?.kind === 'marquee' && state.drag.rect) {
    const [x, y, ww, hh] = state.drag.rect;
    overlay.append(svg('rect', {...boxToScreen([x, y, ww, hh], state), class: 'marquee'}));
  }
  if (state.drag?.kind === 'create' && state.drag.rect) {
    const [x, y, ww, hh] = state.drag.rect;
    overlay.append(svg('rect', {...boxToScreen([x, y, ww, hh], state), class: 'marquee'}));
  }
}

function select(oids, additive = false) {
  const next = additive ? new Set(state.selection) : new Set();
  for (const oid of oids) additive && next.has(oid) ? next.delete(oid) : next.add(oid);
  state.selection = [...next];
  drawOverlay();
  renderLayers();
  renderInspector();
  report();
}

function report() {
  if (!state.scene) return;
  const selected = state.selection.map((oid) => byOid(oid)).filter(Boolean);
  const what = selected.length === 0 ? ''
    : selected.length === 1 ? ` · selected ${selected[0].kind ?? 'element'} ${selected[0].oid}` : '';
  publishContext(`Fignimble ${state.figure} · ${state.scene.size.map((v) => Math.round(v)).join('×')} mm${what}`);
}

// --- edits ------------------------------------------------------------------

async function commit(op, args, what = 'Edit') {
  if (!state.figure || !state.revision) return;
  const result = await invoke('edit', {
    figure: state.figure, expectedRevision: state.revision, snapshotId: state.snapshotId, op, ...args,
  });
  await applyPayload(result.data);
  await refreshFigures();
  setStatus(`${what} saved · ${state.revision.slice(0, 8)}`);
  report();
  saveStateSnapshot();
}

async function commitSelection(op, args = {}, what = 'Edit') {
  if (!state.selection.length) { toast('Select an element first'); return; }
  await commit(op, {oids: state.selection, ...args}, what);
}

function saveStateSnapshot() {
  saveState({figure: state.figure ?? undefined,
             zoom: state.manualZoom ? state.scale : undefined,
             pan: [state.panX, state.panY], selection: state.selection,
             snapshotId: state.snapshotId ?? undefined});
}

async function insertElement(kind, box) {
  const props = kind === 'text' ? {text: 'Text', x: box[0], y: box[1], size: 8}
    : kind === 'line' || kind === 'arrow' ? {x1: box[0], y1: box[1], x2: box[0] + box[2], y2: box[1] + box[3]}
    : kind === 'bracket' ? {x1: box[0], x2: box[0] + box[2], y: box[1]}
    : {x: box[0], y: box[1], w: box[2], h: box[3]};
  const result = await invoke('edit', {
    figure: state.figure, expectedRevision: state.revision, snapshotId: state.snapshotId,
    op: 'insert', kind, props,
  });
  await applyPayload(result.data);
  if (result.data.select?.length) state.selection = result.data.select;
  drawOverlay();
  renderInspector();
  await refreshFigures();
  saveStateSnapshot();
}

async function importPath(path) {
  const [w, h] = state.scene.size;
  const result = await invoke('import_asset', {
    figure: state.figure, path, x: roundMM(w / 4), y: roundMM(h / 4),
    expectedRevision: state.revision, snapshotId: state.snapshotId,
  });
  await applyPayload(result.data);
  await refreshFigures();
  setStatus(`Imported ${path}`);
}

// --- pointer gestures -------------------------------------------------------

function localPoint(event) {
  const box = el('stage').getBoundingClientRect();
  return {x: event.clientX - box.left, y: event.clientY - box.top};
}

el('stage').addEventListener('pointerdown', (event) => {
  if (event.button !== 0) return;
  const target = event.target;
  el('stage').focus();
  const point = screenToMM(localPoint(event), state);
  if (event.altKey && (event.ctrlKey || event.metaKey)) return;
  if (state.tool === 'zoom') { zoomBy(event.altKey ? 1 / 1.3 : 1.3); return; }
  if (state.tool !== 'select' && !target.dataset?.oid) {
    state.drag = {kind: 'create', tool: state.tool, start: point, rect: null, pointer: event.pointerId};
    el('stage').setPointerCapture(event.pointerId);
    event.preventDefault();
    return;
  }
  if (target.dataset.handle === 'se' && state.selection.length === 1) {
    const item = byOid(state.selection[0]);
    if (!item?.box || item.parent || item.host) return;
    state.drag = {kind: 'resize', oid: item.oid, start: point, box: [...item.box], pointer: event.pointerId};
    el('stage').setPointerCapture(event.pointerId);
    return;
  }
  if (target.dataset.divider !== undefined) {
    const item = byOid(state.selection[0]);
    const index = Number(target.dataset.divider);
    if (!item?.dividers?.[index]) return;
    state.drag = {kind: 'divider', oid: item.oid, index, axis: item.dividers[index].axis,
                  start: point, pointer: event.pointerId};
    el('stage').setPointerCapture(event.pointerId);
    return;
  }
  const oid = target.dataset?.oid;
  if (oid) {
    if (event.shiftKey) select([oid], true);
    else if (!state.selection.includes(oid)) select([oid]);
    state.drag = {kind: 'move', start: point, oids: [...state.selection], moved: false, pointer: event.pointerId};
    el('stage').setPointerCapture(event.pointerId);
    event.preventDefault();
    return;
  }
  state.drag = {kind: 'marquee', start: point, base: new Set(event.shiftKey ? state.selection : []),
                rect: null, pointer: event.pointerId};
  if (!event.shiftKey) select([]);
  el('stage').setPointerCapture(event.pointerId);
});

el('stage').addEventListener('pointermove', (event) => {
  const drag = state.drag;
  if (!drag) return;
  const now = screenToMM(localPoint(event), state);
  const dx = now.x - drag.start.x;
  const dy = now.y - drag.start.y;
  if (drag.kind === 'move') {
    if (Math.abs(dx) > 0.05 || Math.abs(dy) > 0.05) drag.moved = true;
    const x = dx * state.scale, y = dy * state.scale;
    for (const oid of drag.oids) {
      const node = nodes.get(oid);
      if (!node) continue;
      node.hit.style.transform = `translate(${x}px, ${y}px)`;
      if (node.img) node.img.style.transform = `translate(${x}px, ${y}px)`;
    }
  } else if (drag.kind === 'marquee' || drag.kind === 'create') {
    drag.rect = rectFromPoints(drag.start, now);
    drawOverlay();
  } else if (drag.kind === 'resize') {
    drag.preview = [drag.box[0], drag.box[1], Math.max(0.5, drag.box[2] + dx), Math.max(0.5, drag.box[3] + dy)];
    const overlay = el('overlay');
    overlay.replaceChildren();
    overlay.append(svg('rect', {...boxToScreen(drag.preview, state), class: 'sel', 'vector-effect': 'non-scaling-stroke'}));
    overlay.append(svg('rect', {
      x: state.panX + (drag.preview[0] + drag.preview[2]) * state.scale - 4,
      y: state.panY + (drag.preview[1] + drag.preview[3]) * state.scale - 4, width: 8, height: 8,
      class: 'handle', 'data-handle': 'se'}));
  }
});

el('stage').addEventListener('pointerup', (event) => {
  const drag = state.drag;
  state.drag = null;
  if (!drag) return;
  try { el('stage').releasePointerCapture(drag.pointer); } catch {}
  if (drag.kind === 'move' && drag.moved) {
    const now = screenToMM(localPoint(event), state);
    const dx = roundMM(now.x - drag.start.x), dy = roundMM(now.y - drag.start.y);
    if (dx || dy) run(() => commit('move', {oids: drag.oids, dx, dy}, 'Move'), 'Move');
    else renderScene();
  } else if (drag.kind === 'move') {
    renderScene();
  } else if (drag.kind === 'marquee') {
    const hits = allElements().filter((item) => item.box && drag.rect && intersects(item.box, drag.rect)).map((item) => item.oid);
    state.selection = [...new Set([...drag.base, ...hits])];
    drawOverlay(); renderLayers(); renderInspector(); report();
  } else if (drag.kind === 'create') {
    const rect = drag.rect && drag.rect[2] > 0.5 && drag.rect[3] > 0.5 ? drag.rect
      : [drag.start.x, drag.start.y, drag.tool === 'text' ? 20 : 12, drag.tool === 'text' ? 4 : 8];
    const tool = drag.tool;
    setTool('select');
    run(() => insertElement(tool, rect.map(roundMM)), `Insert ${tool}`);
  } else if (drag.kind === 'resize' && drag.preview) {
    run(() => commit('resize', {oid: drag.oid, box: drag.preview.map(roundMM)}, 'Resize'), 'Resize');
  } else if (drag.kind === 'divider') {
    const now = screenToMM(localPoint(event), state);
    const delta = roundMM(drag.axis === 'col' ? now.x - drag.start.x : now.y - drag.start.y);
    if (delta) run(() => commit('divider', {oid: drag.oid, index: drag.index, delta}, 'Divider'), 'Divider');
    else renderScene();
  }
});

el('stage').addEventListener('wheel', (event) => {
  if (!event.ctrlKey && !event.metaKey) return;
  event.preventDefault();
  zoomBy(event.deltaY < 0 ? 1.15 : 1 / 1.15);
}, {passive: false});

el('stage').addEventListener('keydown', (event) => {
  if (event.target !== el('stage')) return;
  if (event.key === 'v' || event.key === 'V') setTool('select');
  if (event.key === 'Escape') { setTool('select'); state.selection = []; drawOverlay(); renderLayers(); renderInspector(); return; }
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    run(() => commitSelection('delete', {}, 'Delete'), 'Delete');
    return;
  }
  const steps = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]};
  const step = steps[event.key];
  if (!step) return;
  event.preventDefault();
  const amount = nudgeStep(event.shiftKey, event.altKey);
  run(() => commitSelection('move', {dx: step[0] * amount, dy: step[1] * amount}, 'Nudge'), 'Nudge');
});

// --- toolbar ----------------------------------------------------------------

function setTool(tool) {
  state.tool = tool;
  document.querySelectorAll('#toolbar .tool').forEach((button) => {
    const active = button.dataset.tool === tool;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  el('stage').style.cursor = tool === 'select' ? '' : tool === 'zoom' ? 'zoom-in' : 'crosshair';
}

document.querySelectorAll('#toolbar .tool').forEach((button) => {
  button.addEventListener('click', () => setTool(button.dataset.tool));
});

el('insert-panel').addEventListener('click', () => {
  const path = prompt('Panel file (e.g. panels/scatter.py)');
  if (path) run(() => importPath(path.trim()), 'Place panel');
});

el('insert-picture').addEventListener('click', () => {
  const path = prompt('Picture file in the workspace (e.g. images/cells.png)');
  if (path) run(() => importPath(path.trim()), 'Place picture');
});

el('undo').addEventListener('click', () => run(async () => {
  const result = await invoke('undo', {expectedRevision: state.revision, figure: state.figure});
  await applyPayload(result.data);
  await refreshFigures();
  setStatus(`Undid ${result.data.label ?? ''}`);
}, 'Undo'));

el('redo').addEventListener('click', () => run(async () => {
  const result = await invoke('redo', {expectedRevision: state.revision, figure: state.figure});
  await applyPayload(result.data);
  await refreshFigures();
  setStatus(`Redid ${result.data.label ?? ''}`);
}, 'Redo'));

el('dark').addEventListener('click', () => run(async () => {
  state.dark = !state.dark;
  el('dark').setAttribute('aria-pressed', String(state.dark));
  const result = await invoke('render', {figure: state.figure, dark: state.dark});
  await applyPayload(result.data);
}, 'Dark version'));

el('export').addEventListener('click', () => run(async () => {
  const result = await invoke('export', {figure: state.figure, format: el('format').value,
    dpi: Number(el('dpi').value), expectedRevision: state.revision, dark: state.dark});
  const url = await resourceUrl(result.data.export);
  const link = document.createElement('a');
  link.href = url; link.download = result.data.filename; link.rel = 'noopener';
  document.body.append(link); link.click(); link.remove();
  setStatus(`Exported ${result.data.filename}`);
}, 'Export'));

el('zoom-in').addEventListener('click', () => zoomBy(1.2));
el('zoom-out').addEventListener('click', () => zoomBy(1 / 1.2));
el('fit').addEventListener('click', () => {
  state.zoomChosen = false;
  state.manualZoom = false;
  fitIfNeeded();
  renderScene();
  saveStateSnapshot();
});

function zoomBy(factor) {
  state.scale = Math.max(0.2, Math.min(40, state.scale * factor));
  state.zoomChosen = true;
  state.manualZoom = true;
  renderScene();
  saveStateSnapshot();
}

// --- layers and preflight ---------------------------------------------------

const ICONS = {panel: '▭', image: '▣', text: 'Aa', label: 'a', line: '／', arrow: '↗', rect: '▢',
               ellipse: '◯', bracket: '⌐', layout: '▦', path: '∿', legend: '☰', table: '▤'};

function renderLayers() {
  const list = el('layers');
  list.replaceChildren();
  for (const item of [...allElements()].reverse()) {
    const li = document.createElement('li');
    li.dataset.oid = item.oid;
    li.setAttribute('aria-current', String(state.selection.includes(item.oid)));
    const kind = document.createElement('span');
    kind.className = 'kind';
    kind.textContent = ICONS[item.kind] ?? '·';
    const name = document.createElement('span');
    name.className = 'name';
    const basename = (value) => value ? String(value).split('/').pop() : '';
    const label = item.kind === 'label' ? `label ${item.text ?? item.props?.text ?? ''}`
      : item.kind === 'text' ? `“${String(item.props?.text ?? '').slice(0, 18)}”`
      : item.kind === 'panel' ? basename(item.props?.source)
      : item.kind === 'image' ? basename(item.props?.source)
      : item.kind === 'layout' ? 'layout' : item.oid;
    name.textContent = label;
    const hidden = document.createElement('button');
    hidden.className = 'toggle' + (item.props?.hidden ? ' off' : '');
    hidden.textContent = item.props?.hidden ? '◌' : '◉';
    hidden.title = item.props?.hidden ? 'Show' : 'Hide';
    hidden.addEventListener('click', (event) => {
      event.stopPropagation();
      run(() => commit('set', {oid: item.oid, props: {hidden: !item.props?.hidden}}, 'Hide'), 'Hide');
    });
    const locked = document.createElement('button');
    locked.className = 'toggle' + (item.props?.locked ? '' : ' off');
    locked.textContent = item.props?.locked ? '🔒' : '🔓';
    locked.title = item.props?.locked ? 'Unlock' : 'Lock';
    locked.addEventListener('click', (event) => {
      event.stopPropagation();
      run(() => commit('set', {oid: item.oid, props: {locked: !item.props?.locked}}, 'Lock'), 'Lock');
    });
    li.append(kind, name, hidden, locked);
    li.addEventListener('click', (event) => select([item.oid], event.shiftKey));
    list.append(li);
  }
}

function renderWarnings() {
  const list = el('warnings');
  list.replaceChildren();
  const warnings = state.scene?.warnings ?? [];
  if (!warnings.length) {
    const empty = document.createElement('li');
    empty.className = 'empty';
    empty.textContent = 'No preflight warnings.';
    list.append(empty);
    return;
  }
  for (const warning of warnings) {
    const li = document.createElement('li');
    li.textContent = warning.message;
    li.dataset.level = warning.level;
    li.addEventListener('click', () => { if (warning.oid) select([warning.oid]); });
    list.append(li);
  }
}

// --- inspector --------------------------------------------------------------

function current() {
  return state.selection.length === 1 ? byOid(state.selection[0]) : null;
}

function renderInspector() {
  const item = current();
  const title = el('selection-title');
  const kind = el('selection-kind');
  if (!item) {
    title.textContent = 'Figure';
    kind.textContent = state.scene ? `${Math.round(state.scene.size[0])} × ${Math.round(state.scene.size[1])} mm` : '';
  } else {
    title.textContent = item.props?.source ?? item.oid;
    kind.textContent = item.kind ?? '';
  }
  const disabled = !item;
  const geometryTaken = Boolean(item?.parent || item?.host);
  for (const id of ['f-x', 'f-y', 'f-w', 'f-h', 'f-turn', 'f-label', 'f-label-text',
                    'f-locked', 'f-hidden', 'edit-code', 'refresh-code']) {
    el(id).disabled = disabled;
  }
  for (const id of ['f-x', 'f-y', 'f-w', 'f-h']) {
    el(id).disabled = disabled || geometryTaken;
    el(id).title = geometryTaken ? 'Placed by its layout; move or resize the layout' : '';
  }
  el('panel-texts').replaceChildren();
  el('made-by').textContent = '';
  el('code-ref').textContent = '—';
  if (!item) return;
  const box = item.box ?? [0, 0, 0, 0];
  el('f-x').value = box[0]; el('f-y').value = box[1];
  el('f-w').value = box[2]; el('f-h').value = box[3];
  const props = item.props ?? {};
  el('f-turn').value = Number(props.rotation ?? 0);
  el('f-turn').disabled = disabled || !['image', 'panel'].includes(item.kind);
  el('f-locked').checked = Boolean(props.locked);
  el('f-hidden').checked = Boolean(props.hidden);
  const label = props.label;
  el('f-label').value = label === null || label === 'none' ? 'none' : 'auto';
  el('f-label-text').value = typeof label === 'string' && label !== 'auto' ? label : '';

  const source = props.source ?? item.code?.file ?? state.scene?.file ?? '';
  el('code-ref').textContent = source || '—';
  const site = item.site ?? item.code ?? {};
  const where = site.file ? `${site.file.split('/').pop()}${site.line ? `, line ${site.line}` : ''}` : '';
  el('made-by').textContent = where ? `Made by ${where}.` : '';
  el('source-site').textContent = item.kind === 'panel' && props.source
    ? `placed by ${state.scene?.file ?? ''}${site.line ? `, line ${site.line}` : ''}` : '';

  for (const text of item.texts ?? []) {
    const li = document.createElement('li');
    const input = document.createElement('input');
    input.value = text.text ?? '';
    input.setAttribute('aria-label', `Panel text ${text.key}`);
    input.addEventListener('change', () => run(() => commit('panel_text',
      {oid: item.oid, key: text.key, text: input.value, old: text.text}, 'Panel text'), 'Panel text'));
    li.append(input);
    el('panel-texts').append(li);
  }
}

function inspectorEdit(op, args) {
  const item = current();
  if (!item) return;
  run(() => commit(op, args(item), 'Inspector'), 'Inspector');
}

el('f-x').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {x: Number(el('f-x').value)}})));
el('f-y').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {y: Number(el('f-y').value)}})));
el('f-w').addEventListener('change', () => inspectorEdit('resize', (item) => ({
  oid: item.oid, box: [item.box[0], item.box[1], Math.max(0.5, Number(el('f-w').value)), item.box[3]]})));
el('f-h').addEventListener('change', () => inspectorEdit('resize', (item) => ({
  oid: item.oid, box: [item.box[0], item.box[1], item.box[2], Math.max(0.5, Number(el('f-h').value))]})));
el('f-turn').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {rotation: Number(el('f-turn').value)}})));
el('f-locked').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {locked: el('f-locked').checked}})));
el('f-hidden').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {hidden: el('f-hidden').checked}})));
el('f-label').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {label: el('f-label').value === 'none' ? null : 'auto'}})));
el('f-label-text').addEventListener('change', () => inspectorEdit('set', (item) => ({oid: item.oid, props: {label: el('f-label-text').value || 'auto'}})));

el('edit-code').addEventListener('click', () => run(async () => {
  const item = current();
  const file = item?.props?.source ?? state.scene?.file;
  if (!file) return;
  await loadSource(file);
  showPane('code');
}, 'Edit code'));
el('refresh-code').addEventListener('click', () => run(async () => {
  const result = await invoke('figure', {figure: state.figure, pxPerMM: 12});
  await applyPayload(result.data, {keepSelection: true});
}, 'Refresh'));

el('arr-front').addEventListener('click', () => run(() => commitSelection('order', {how: 'front'}, 'Order'), 'Order'));
el('arr-back').addEventListener('click', () => run(() => commitSelection('order', {how: 'back'}, 'Order'), 'Order'));
el('arr-dup').addEventListener('click', () => run(() => commitSelection('duplicate', {dx: 5, dy: 5}, 'Duplicate'), 'Duplicate'));
el('arr-del').addEventListener('click', () => run(() => commitSelection('delete', {}, 'Delete'), 'Delete'));

const ALIGNS = [['left', 'Align left'], ['center', 'Align centre'], ['right', 'Align right'],
                ['top', 'Align top'], ['middle', 'Align middle'], ['bottom', 'Align bottom']];
for (const [how, title] of ALIGNS) {
  const button = document.createElement('button');
  button.title = title;
  button.setAttribute('aria-label', title);
  button.innerHTML = `<svg viewBox="0 0 16 16"><rect x="3" y="4" width="6" height="8" rx="1" fill="none" stroke="currentColor" stroke-width="1.1"/><path d="${
    how === 'left' ? 'M2 2v12' : how === 'right' ? 'M14 2v12' : how === 'top' ? 'M2 2h12' : how === 'bottom' ? 'M2 14h12'
      : how === 'center' ? 'M8 2v12' : 'M2 8h12'}" stroke="currentColor" stroke-width="1.2"/></svg>`;
  button.addEventListener('click', () => run(() => commitSelection('align', {how, to: 'figure'}, 'Align'), 'Align'));
  el('align-figure').append(button);
}

// --- source -----------------------------------------------------------------

async function sourceFiles() {
  const files = [];
  if (state.scene?.file) files.push(state.scene.file);
  files.push('style.py');
  const item = current();
  const panel = item?.props?.source;
  if (panel && panel.endsWith('.py')) files.push(panel);
  return [...new Set(files)];
}

async function retargetSource() {
  const selectNode = el('source-file');
  const files = await sourceFiles();
  const currentFile = el('source-text').dataset.file;
  selectNode.replaceChildren();
  for (const file of files) {
    const option = document.createElement('option');
    option.value = file; option.textContent = file;
    selectNode.append(option);
  }
  if (currentFile && files.includes(currentFile)) {
    selectNode.value = currentFile;
  } else if (files.length) {
    await loadSource(files[0]);
  }
}

async function loadSource(file) {
  const result = await invoke('source', {file});
  state.fileRevision = result.data.revision;
  state.sourceDirty = false;
  el('source-text').value = result.data.text;
  el('source-text').dataset.file = file;
  el('source-file').value = file;
  if (result.data.truncated) toast(`Showing the first lines of ${file} (${result.data.totalLines} total)`);
}

el('source-file').addEventListener('change', () => run(() => loadSource(el('source-file').value), 'Load source'));
el('source-reload').addEventListener('click', () => run(() => loadSource(el('source-text').dataset.file), 'Reload source'));
el('source-text').addEventListener('input', () => { state.sourceDirty = true; });
el('source-save').addEventListener('click', () => run(async () => {
  const file = el('source-text').dataset.file;
  if (!file) return;
  try {
    const result = await invoke('edit_source', {file, text: el('source-text').value,
      expectedRevision: state.fileRevision, figure: state.figure});
    state.fileRevision = result.data.fileRevision ?? result.data.revision;
    state.sourceDirty = false;
    await applyPayload(result.data);
    setStatus(`Saved ${file}`);
    await refreshFigures();
  } catch (error) {
    if (error.code === 'STALE_REVISION') { await loadSource(file); toast('File changed elsewhere; reloaded it', true); }
    throw error;
  }
}, 'Save source'));

// --- bottom pane ------------------------------------------------------------

function showPane(pane) {
  state.pane = pane;
  el('code-pane').hidden = pane !== 'code';
  el('preflight-pane').hidden = pane !== 'preflight';
  document.querySelectorAll('#bottom-tabs button').forEach((button) => {
    const active = button.dataset.pane === pane;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}
document.querySelectorAll('#bottom-tabs button').forEach((button) => {
  button.addEventListener('click', () => showPane(button.dataset.pane));
});

// --- figures, assets, poll --------------------------------------------------

el('new-figure').addEventListener('click', () => {
  const name = prompt('New figure name', 'fig2');
  if (!name) return;
  run(async () => {
    const result = await invoke('new_figure', {name: name.trim(), width: 183, height: 120, expectedRevision: state.revision});
    await refreshFigures();
    await openFigure(result.data.figure);
  }, 'New figure');
});

async function poll() {
  try {
    const result = await invoke('editor_state', {afterVersion: state.version});
    const data = result.data;
    const first = state.version < 0;
    state.version = data.version;
    if (first) { setTimeout(poll, 1000); return; }
    if (data.changed && state.figure && !state.drag && !state.busy && !state.sourceDirty) {
      const figureResult = await invoke('figure', {figure: state.figure, pxPerMM: 12});
      await applyPayload(figureResult.data, {keepSelection: true});
      await refreshFigures();
      await retargetSource();
    }
  } catch (error) {
    /* a closed instance is reported by the next action */
  }
  setTimeout(poll, document.hidden ? 5000 : 1000);
}

// --- boot -------------------------------------------------------------------

async function step(name, fn) {
  try {
    return await fn();
  } catch (error) {
    error.step = error.step ?? name;
    throw error;
  }
}

(async () => {
  try {
    await step('connect', connect);
    const stateResult = await step('project state', () => invoke('state', {limit: 200}));
    const figures = stateResult.data.figures;
    if (!figures.length) {
      setStatus('This folder has no figure yet; press + to make one');
    } else {
      const wanted = saved.figure && figures.some((figure) => figure.name === saved.figure)
        ? saved.figure : figures[0].name;
      await step('open figure', () => openFigure(wanted, {restore: Boolean(saved.figure)}));
    }
    await step('figures', refreshFigures);
    poll();
  } catch (error) {
    const detail = error.step ? `${error.step}: ${error.message}` : error.message;
    window.__lastFailure = {detail, stack: String(error.stack ?? '')};
    setStatus(detail, true);
    toast(detail, true);
  }
})();
