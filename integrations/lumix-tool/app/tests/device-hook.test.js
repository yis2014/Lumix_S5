const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// The hook's async actions keep their state in a ref. A small hook adapter lets
// us exercise the actual actions without adding a DOM/test renderer dependency.
function mount(api) {
  let latest;
  const cleanups = [];
  const React = {
    useState: initial => { latest = initial; return [initial, value => { latest = value; }]; },
    useRef: initial => ({ current: initial }), useCallback: callback => callback,
    useEffect: callback => { cleanups.push(callback()); },
  };
  const source = fs.readFileSync(path.join(__dirname, '../src/hooks/useDevice.js'), 'utf8')
    .replace(/^import .* from 'react';/m, 'const { useCallback, useEffect, useRef, useState } = React;')
    .replace('export function useDevice', 'function useDevice');
  const context = { React, window: { addEventListener() {}, removeEventListener() {} } };
  vm.runInNewContext(`${source}\nthis.mount = useDevice;`, context);
  const actions = context.mount(api);
  return { actions, state: () => latest, unmount: () => cleanups.forEach(cleanup => cleanup?.()) };
}

async function settleUntil(predicate) {
  for (let turn = 0; turn < 20; turn++) {
    if (predicate()) return;
    await new Promise(resolve => setImmediate(resolve));
  }
  assert.fail('Hook did not settle.');
}

test('driver install works without Python/camera readiness and holds UI lock through follow-up detection', async t => {
  let finishInstall;
  let finishFollowup;
  let statusCalls = 0;
  let installs = 0;
  let driverOk = false;
  const api = {
    env: async () => ({ platform: 'win32', python: null, mock: false }),
    driverStatus: async () => ({ supported: true, present: true, ok: driverOk }),
    status: async () => {
      statusCalls++;
      if (statusCalls === 2) return new Promise(resolve => { finishFollowup = resolve; });
      return { connected: false, pythonMissing: true };
    },
    onProgress: () => () => {},
    installDriver: () => { installs++; return new Promise(resolve => { finishInstall = resolve; }); },
    uninstallDriver: () => { throw new Error('locked'); },
  };
  const hook = mount(api);
  t.after(hook.unmount);
  await settleUntil(() => !hook.state().checking);
  const pending = hook.actions.runDriver('install');
  assert.equal(hook.state().busy.tool, 'driver');
  await hook.actions.runDriver('install');
  await hook.actions.runDriver('uninstall');
  await hook.actions.refreshDriver();
  assert.equal(installs, 1);
  driverOk = true;
  finishInstall({ ok: true, message: 'added', step: 'complete', pnputilExit: 0, output: '' });
  await settleUntil(() => !!finishFollowup);
  assert.equal(hook.state().checking, true);
  assert.equal(hook.state().busy, null);
  await hook.actions.runDriver('install');
  assert.equal(installs, 1);
  finishFollowup({ connected: false, pythonMissing: true });
  await pending;
  assert.equal(hook.state().checking, false);
  assert.equal(hook.state().driver.ok, true);
  assert.equal(hook.state().driverResult.ok, true);
});

test('UAC cancellation and IPC rejection remain visible and leave driver actions usable', async t => {
  let outcome = 'cancelled';
  const api = {
    env: async () => ({ platform: 'win32', python: null }),
    driverStatus: async () => ({ supported: true, present: true, ok: false }),
    status: async () => ({ connected: false }), onProgress: () => () => {},
    installDriver: async () => {
      if (outcome === 'reject') throw new Error('IPC disconnected');
      return { ok: false, cancelled: true, message: 'cancelled' };
    },
  };
  const hook = mount(api);
  t.after(hook.unmount);
  await settleUntil(() => !hook.state().checking);
  await hook.actions.runDriver('install');
  assert.equal(hook.state().driverResult.cancelled, true);
  assert.equal(hook.state().busy, null);
  assert.equal(hook.state().checking, false);
  outcome = 'reject';
  await hook.actions.runDriver('install');
  assert.equal(hook.state().driverResult.ok, false);
  assert.equal(hook.state().driverResult.message, 'IPC disconnected');
  assert.equal(hook.state().checking, false);
});
