import assert from 'node:assert/strict';
import test from 'node:test';
import { runSingleFlight } from './singleFlight.js';

test('single-flight guard ignores duplicate clicks until the active request settles', async () => {
  const lock = { current: false };
  let resolveRequest;
  let calls = 0;
  const activeRequest = runSingleFlight(lock, () => {
    calls += 1;
    return new Promise((resolve) => { resolveRequest = resolve; });
  });

  assert.equal(await runSingleFlight(lock, async () => { calls += 1; }), undefined);
  assert.equal(calls, 1);

  resolveRequest('complete');
  assert.equal(await activeRequest, 'complete');
  assert.equal(lock.current, false);
});

test('single-flight guard releases after a failed request so retry is possible', async () => {
  const lock = { current: false };
  await assert.rejects(
    runSingleFlight(lock, async () => { throw new Error('request failed'); }),
    /request failed/,
  );

  assert.equal(lock.current, false);
  assert.equal(await runSingleFlight(lock, async () => 'retried'), 'retried');
});
