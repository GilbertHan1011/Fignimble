import test from 'node:test';
import assert from 'node:assert/strict';
import {asRef} from '../web/bridge.mjs';

test('a sprite is sent as a bare ResourceRef', () => {
  const sprite = {uri: 'workspace:///a.png', type: 'fignimble.sprite', mimeType: 'image/png',
                  revision: 'abc', x: 4, y: 6, w: 20, h: 10};
  assert.deepEqual(asRef(sprite), {uri: 'workspace:///a.png', type: 'fignimble.sprite',
                                   mimeType: 'image/png', revision: 'abc'});
});

test('missing optional fields stay missing', () => {
  assert.deepEqual(asRef({uri: 'workspace:///b', type: 'fignimble.source'}),
                   {uri: 'workspace:///b', type: 'fignimble.source'});
});
