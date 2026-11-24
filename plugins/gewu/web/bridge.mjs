// The GeWu view bridge: one MessagePort, every canvas action is a plugin tool call.
const pending = new Map();
let serial = 0;
let rpc = null;
let epoch = null;
export let saved = {};
export let context = {};

export function connect() {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('GeWu did not bind this view')), 15000);
    window.addEventListener('message', ({source, data, ports}) => {
      if (source !== parent || data?.type !== 'gewu.view.bound' || !ports[0]) return;
      clearTimeout(timer);
      const port = ports[0];
      epoch = data.context.viewEpoch;
      saved = data.context.state ?? {};
      context = data.context;
      port.onmessage = ({data: reply}) => {
        const entry = pending.get(reply.id);
        if (!entry) return;
        pending.delete(reply.id);
        if (reply.error) entry.reject(Error(reply.error)); else entry.resolve(reply.result);
      };
      rpc = (method, params) => new Promise((done, fail) => {
        const id = ++serial;
        pending.set(id, {resolve: done, reject: fail});
        port.postMessage({id, method, params, viewEpoch: epoch});
      });
      resolve(data.context);
    }, {once: true});
    parent.postMessage({type: 'gewu.view.ready'}, '*');
  });
}

export async function invoke(tool, args = {}) {
  const {callId} = await rpc('callTool', {tool, args});
  for (let tries = 0; tries < 2400; tries++) {
    const call = await rpc('getCall', {callId});
    if (call.status === 'running') { await new Promise((r) => setTimeout(r, 200)); continue; }
    if (call.status !== 'succeeded' || !call.result?.ok) {
      const error = call.result?.error;
      const failure = Error(error?.message ?? `The ${tool} call ${call.status}`);
      failure.code = error?.code;
      throw failure;
    }
    return call.result;
  }
  throw Error(`The ${tool} call did not settle`);
}

const urls = new Map();
const REF_FIELDS = ['uri', 'type', 'mimeType', 'revision'];

// The host accepts exactly a ResourceRef; sprites also carry mm boxes, which
// must stay in the page and never go over the bridge.
export function asRef(ref) {
  const clean = {};
  for (const field of REF_FIELDS) if (field in ref) clean[field] = ref[field];
  return clean;
}

export async function resourceUrl(ref) {
  if (!ref) return null;
  const clean = asRef(ref);
  const key = `${clean.uri}@${clean.revision ?? ''}`;
  if (!urls.has(key)) urls.set(key, (await rpc('resolveResource', {resource: clean})).url);
  return urls.get(key);
}

export function publishContext(summary) {
  rpc?.('publishContext', {summary: summary.slice(0, 2000)}).catch(() => {});
}

export function saveState(state) {
  rpc?.('saveState', {state}).catch(() => {});
}
