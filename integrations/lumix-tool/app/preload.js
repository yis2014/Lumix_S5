const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('api', {
  env: () => ipcRenderer.invoke('env'),
  pickPython: () => ipcRenderer.invoke('pick-python'),
  pickAudio: () => ipcRenderer.invoke('pick-audio'),
  status: () => ipcRenderer.invoke('status'),
  driverStatus: () => ipcRenderer.invoke('driver-status'),
  installDriver: () => ipcRenderer.invoke('driver-install'),
  uninstallDriver: options => ipcRenderer.invoke('driver-uninstall', options),
  openZadig: () => ipcRenderer.invoke('open-external', 'https://zadig.akeo.ie/'),
  readFile: path => ipcRenderer.invoke('read-file', path),
  pathForFile: file => webUtils.getPathForFile(file),
  apply: (pcm, samples) => ipcRenderer.invoke('apply', { pcm, samples }),
  restore: () => ipcRenderer.invoke('restore'),
  dump: () => ipcRenderer.invoke('dump'),
  scanMemory: () => ipcRenderer.invoke('scan-memory'),
  memoryMap: version => ipcRenderer.invoke('memory-map', version),
  exportMemory: version => ipcRenderer.invoke('export-memory', version),
  applySlot: (index, pcm, samples, version) => ipcRenderer.invoke('apply-slot', { index, pcm, samples, version }),
  applySlots: (indices, pcm, samples, version) => ipcRenderer.invoke('apply-slots', { indices, pcm, samples, version }),
  restoreId: (index, version) => ipcRenderer.invoke('restore-id', { index, version }),
  restoreAll: version => ipcRenderer.invoke('restore-all', { version }),
  renameSound: (version, index, label) => ipcRenderer.invoke('rename-sound', { version, index, label }),
  configureMock: options => ipcRenderer.invoke('mock-configure', options),
  onProgress: callback => {
    const listener = (_event, progress) => callback(progress);
    ipcRenderer.on('progress', listener);
    return () => ipcRenderer.removeListener('progress', listener);
  },
});
