import { useCallback, useEffect, useRef, useState } from 'react';

const initialState = { env: null, device: {}, driver: null, driverResult: null, driverChecking: false, busy: null, checking: false, configuring: false, progress: null, error: '' };
const locked = state => !!state.busy || state.checking || state.configuring || state.driverChecking;
// Background driver polling must not grey out the primary "use the tools" action.
const actionLocked = state => !!state.busy || state.checking || state.configuring;

export function useDevice(api) {
  const [state, setState] = useState(initialState);
  const current = useRef(initialState);
  const patch = useCallback(values => {
    current.current = { ...current.current, ...values };
    setState(current.current);
  }, []);

  const readDriver = useCallback(async () => {
    try {
      const driver = await api.driverStatus();
      if (driver.busy) throw new Error(driver.error || '另一个操作正在进行。');
      patch({ driver });
    } catch (error) {
      patch({ driver: { supported: current.current.env?.platform === 'win32' || current.current.env?.mock, ok: false, error: error.message || String(error) } });
    }
  }, [api, patch]);

  const readDevice = useCallback(async () => {
    const env = await api.env();
    patch({ env });
    await readDriver();
    const device = await api.status();
    if (device.busy) throw new Error(device.error || '另一个操作正在进行，请稍后刷新。');
    patch({ env, device });
  }, [api, patch, readDriver]);

  const refreshDriver = useCallback(async () => {
    if (locked(current.current)) return;
    patch({ driverChecking: true });
    try { await readDriver(); }
    finally { patch({ driverChecking: false }); }
  }, [patch, readDriver]);

  const runDriver = useCallback(async (action, options) => {
    if (locked(current.current) || !current.current.driver?.supported) return;
    patch({ busy: { tool: 'driver', label: action === 'install' ? '正在安装驱动' : '正在卸载驱动' }, driverResult: null });
    try {
      const result = action === 'install' ? await api.installDriver() : await api.uninstallDriver(options);
      patch({ driverResult: { ...result, action } });
    } catch (error) {
      patch({ driverResult: { ok: false, action, message: error.message || String(error) } });
    } finally {
      patch({ busy: null, checking: true });
      try { await readDevice(); }
      catch (error) { patch({ device: { connected: false, error: error.message || String(error) } }); }
      finally { patch({ checking: false }); }
    }
  }, [api, patch, readDevice]);

  const refreshDevice = useCallback(async () => {
    if (locked(current.current)) return;
    patch({ checking: true, error: '' });
    try { await readDevice(); }
    catch (error) { patch({ env: current.current.env || { python: null }, device: { connected: false, error: error.message || String(error) } }); }
    finally { patch({ checking: false }); }
  }, [patch, readDevice]);

  useEffect(() => {
    const unsubscribe = api.onProgress(progress => {
      if (current.current.busy && Number.isFinite(progress.done) && Number.isFinite(progress.total) && progress.total > 0) {
        patch({ progress });
      }
    });
    void refreshDevice();
    const preventDropNavigation = event => event.preventDefault();
    window.addEventListener('dragover', preventDropNavigation);
    window.addEventListener('drop', preventDropNavigation);
    return () => {
      unsubscribe();
      window.removeEventListener('dragover', preventDropNavigation);
      window.removeEventListener('drop', preventDropNavigation);
    };
  }, [api, patch, refreshDevice]);

  const configureMock = useCallback(async options => {
    if (locked(current.current)) return;
    patch({ configuring: true, error: '' });
    try {
      const result = await api.configureMock(options);
      if (!result.ok) throw new Error(result.error);
      await readDevice();
    } catch (error) { patch({ error: error.message || String(error) }); }
    finally { patch({ configuring: false }); }
  }, [api, patch, readDevice]);

  const pickPython = useCallback(async () => {
    if (locked(current.current) || current.current.env?.mock) return null;
    patch({ configuring: true });
    try {
      const result = await api.pickPython();
      if (result?.ok) await readDevice();
      return result;
    } catch (error) { return { ok: false, error: error.message || String(error) }; }
    finally { patch({ configuring: false }); }
  }, [api, patch, readDevice]);

  const runOperation = useCallback(async ({ tool, label, execute }) => {
    const snapshot = current.current;
    if (locked(snapshot) || !snapshot.env?.python || !snapshot.device.connected || snapshot.device.error || snapshot.device.pythonMissing) {
      throw new Error('设备尚未就绪，请检查连接并等待当前操作完成。');
    }
    patch({ busy: { tool, label }, progress: null });
    try { return await execute(); }
    finally {
      // Keep all conflicting actions locked through the follow-up status read.
      patch({ busy: null, checking: true });
      try { await readDevice(); }
      catch (error) { patch({ device: { connected: false, error: error.message || String(error) } }); }
      finally { patch({ checking: false }); }
    }
  }, [patch, readDevice]);

  return {
    ...state, api,
    ready: !!state.env?.python && !!state.device.connected && !state.device.error && !state.device.pythonMissing && !!state.device.soundTable?.ok,
    locked: locked(state) || !state.env,
    actionLocked: actionLocked(state) || !state.env,
    refreshDevice, refreshDriver, runDriver, configureMock, pickPython, runOperation,
  };
}
