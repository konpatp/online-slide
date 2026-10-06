import {test} from 'node:test';
import assert from 'node:assert/strict';
const listeners: Record<string, () => void> = {};
(globalThis as any).document = {hidden: false, addEventListener: (name: string, f: () => void) => {listeners[name] = f;}};
(globalThis as any).window = {addEventListener: (name: string, f: () => void) => {listeners[name] = f;}};
import {createLiveUpdates} from '../../src/editor/live';

function host(answer: string, during?: () => void) {
  const seen: string[] = [];
  let token = '1:a';
  const live = createLiveUpdates({
    token: () => token,
    request: async () => { during?.call(null); if (during) token = '2:b';
      return {ok: true, json: async () => ({token: answer})} as unknown as Response; },
    changed: v => { seen.push(v.token); },
    enabled: () => true,
  }, 60000);
  return {live, seen};
}
const settle = () => new Promise(resolve => setTimeout(resolve, 10));

test('a newer deck on the server is pulled', async () => {
  const {live, seen} = host('2:b'); live.start(); await settle();
  live.stop(); assert.deepEqual(seen, ['2:b']);
});
test('an answer overtaken by our own save or creation is stale and ignored', async () => {
  const {live, seen} = host('1:a', () => {}); live.start(); await settle();
  live.stop(); assert.deepEqual(seen, []);
});
test('an unchanged deck is not pulled', async () => {
  const {live, seen} = host('1:a'); live.start(); await settle();
  live.stop(); assert.deepEqual(seen, []);
});
