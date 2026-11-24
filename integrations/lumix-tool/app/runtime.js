const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { StringDecoder } = require('node:string_decoder');
const { DriverManager, DRIVER_SCENARIOS, DRIVER_RESULTS } = require('./driver');
const mockTable = require('./mock-sound-table.json');
const { START, END, BLOCK, validMap, liveRegions, planAllocation, markRange, mockMemoryMap, hexAddress } = require('./memory.mjs');
const SCRATCH_VIRTUAL = START - 0x80000000;
const isScratch = addr => Number(addr) >= SCRATCH_VIRTUAL && Number(addr) < END - 0x80000000;
// Stock sound-table entries point into the firmware program image (virtual
// 0x06280000..0x07280000 on 2.90). Anything else was patched, including entries
// written to the 0x8B5B0000 scratch briefly used in commit e59b596.
const isStockAddress = addr => Number(addr) >= 0x06280000 && Number(addr) < 0x07280000;
const validIndex = index => Number.isInteger(index) && index >= 0 && index < 28;
const validHex = hex => typeof hex === 'string' && /^[0-9a-f]{64}$/i.test(hex);

function pcmBuffer(payload) {
  if (!payload || !Number.isInteger(payload.samples) || payload.samples < 1 || payload.samples > 132300) {
    throw new Error('采样数量无效：音频必须大于 0 秒且不超过 3 秒。');
  }
  let pcm;
  try { pcm = Buffer.from(payload.pcm); } catch { throw new Error('PCM 数据无效。'); }
  if (pcm.length !== payload.samples * 2) throw new Error('PCM size mismatch');
  return pcm;
}

// Keep partial stdout lines: PROGRESS and final JSON can be split anywhere.
function lineReader(callback) {
  const decoder = new StringDecoder('utf8');
  let pending = '';
  function consume(text, finish = false) {
    pending += text;
    const lines = pending.split(/\r?\n/);
    pending = lines.pop();
    if (finish && pending) { lines.push(pending); pending = ''; }
    for (const line of lines) if (line.trim()) callback(line.trim());
  }
  return { write: chunk => consume(decoder.write(chunk)), end: () => consume(decoder.end(), true) };
}

function parseResult({ code, stdout, stderr }) {
  const last = stdout.trim().split(/\r?\n/).filter(Boolean).pop();
  try {
    const value = JSON.parse(last);
    if (value && typeof value === 'object' && !Array.isArray(value) && code === 0) return value;
  } catch {}
  return { ok: false, connected: false, error: [stderr.trim(), stdout.trim()].filter(Boolean).join('\n') || `后端未返回有效结果（退出码 ${code}）。` };
}

class Runtime {
  constructor({ configPath, legacyConfigPath, scriptPath, bundledPython = null, mock = false, onProgress = () => {}, platform = process.platform }) {
    Object.assign(this, { configPath, legacyConfigPath, scriptPath, bundledPython, mock, onProgress, platform });
    this.python = null;
    this.mockState = { scenario: 'connected', failNext: false, custom: false, driverScenario: 'ok', driverResult: 'success' };
    this.driver = new DriverManager({ platform, mock, mockState: this.mockState });
    this.mockEntries = mockTable.map(entry => ({ ...entry }));
    this.soundsPath = path.join(path.dirname(configPath), mock ? 'sounds-mock.json' : 'sounds.json');
    this.memoryPath = path.join(path.dirname(configPath), mock ? 'memory-maps-mock.json' : 'memory-maps.json');
    if (mock) {
      this.mockRam = Buffer.alloc(END - START, 0x55);
      for (const item of mockMemoryMap().runs) if (item.kind !== 'free-0x55') {
        this.mockRam.fill(item.kind === 'zero' ? 0 : 0xA7, Number(item.start) - START, Number(item.end) - START);
      }
    }
    this.batchContext = null;
    // Never overwrite the new config, even if the legacy file is newer.
    if (!fs.existsSync(configPath) && fs.existsSync(legacyConfigPath)) {
      fs.mkdirSync(path.dirname(configPath), { recursive: true });
      fs.copyFileSync(legacyConfigPath, configPath, fs.constants.COPYFILE_EXCL);
    }
  }

  loadConfig() {
    try { return JSON.parse(fs.readFileSync(this.configPath, 'utf8')); } catch { return {}; }
  }

  loadSounds() {
    try { return JSON.parse(fs.readFileSync(this.soundsPath, 'utf8')); }
    catch (error) {
      if (error.code === 'ENOENT') return {};
      throw new Error(`无法读取音效备份，请检查 ${this.soundsPath}：${error.message}`);
    }
  }

  saveSounds(sounds) {
    fs.mkdirSync(path.dirname(this.soundsPath), { recursive: true });
    const temporary = `${this.soundsPath}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify(sounds, null, 2));
    fs.renameSync(temporary, this.soundsPath);
  }

  emitProgress(progress) {
    if (this.progressPhase) progress = { ...progress, phase: this.progressPhase };
    const batch = this.batchContext;
    this.onProgress(batch ? { ...progress, ...batch,
      overallDone: batch.completedUnits + progress.done,
      overallTotal: batch.count * progress.total } : progress);
  }

  async dump() {
    if (this.mock) {
      if (!['connected', 'region-not-free', 'unverified'].includes(this.mockState.scenario)) return { ok: false, error: '模拟设备未就绪。' };
      return { ok: true, entries: this.mockEntries.map(entry => ({ ...entry })) };
    }
    if (this.platform !== 'win32') return { ok: false, error: '实机读取需要 Windows WinUSB 环境。' };
    return this.run(['dump']);
  }

  async soundTable(version) {
    if (typeof version !== 'string' || !/^0x[0-9a-f]{4}$/i.test(version)) return { ok: false, error: '无法识别机身版本，未保存音效备份。' };
    const table = await this.dump();
    if (!table.ok) return table;
    if (table.entries?.length !== 28 || new Set(table.entries.map(e => e.index)).size !== 28 ||
        table.entries.some(e => !validIndex(e.index) || !validHex(e.hex))) return { ok: false, error: '音效表数据不完整，未保存备份。' };
    const sounds = this.loadSounds();
    const key = version.toLowerCase();
    const saved = sounds[key] || { originals: {}, labels: {} };
    saved.originals ||= {};
    saved.labels ||= {};
    for (const entry of table.entries) {
      const raw = Buffer.from(entry.hex, 'hex');
      if (isStockAddress(raw.readUInt32LE(4)) && !Object.hasOwn(saved.originals, entry.index)) {
        saved.originals[entry.index] = entry.hex;
      }
    }
    sounds[key] = saved;
    this.saveSounds(sounds);
    return { ...table, version: key, ...saved };
  }

  async inspect() {
    const status = await this.status();
    if (!status.connected || status.error) return status;
    const soundTable = await this.soundTable(status.body_version);
    return { ...status, soundTable, ...(soundTable.ok ? {} : { error: soundTable.error }),
      memoryMap: this.memoryMap(status.body_version).map,
      custom: soundTable.ok ? liveRegions(soundTable.entries).length > 0 : status.custom };
  }

  loadMemoryMaps() {
    try {
      const maps = JSON.parse(fs.readFileSync(this.memoryPath, 'utf8'));
      return maps && typeof maps === 'object' && !Array.isArray(maps) ? maps : {};
    }
    catch (error) {
      if (error.code === 'ENOENT' || error instanceof SyntaxError) return {};
      throw new Error(`无法读取内存扫描缓存，请检查 ${this.memoryPath}：${error.message}`);
    }
  }

  memoryMap(version) {
    if (typeof version !== 'string' || !/^0x[0-9a-f]{4}$/i.test(version)) return { ok: false, map: null, error: '无法识别机身版本。' };
    const key = version.toLowerCase();
    const map = this.loadMemoryMaps()[key];
    return { ok: true, map: validMap(map) && map.bodyVersion === key ? map : null };
  }

  saveMemoryMap(map) {
    if (!validMap(map)) throw new Error('内存扫描数据无效，请重新扫描。');
    const maps = this.loadMemoryMaps();
    maps[map.bodyVersion] = map;
    fs.mkdirSync(path.dirname(this.memoryPath), { recursive: true });
    fs.writeFileSync(`${this.memoryPath}.tmp`, JSON.stringify(maps, null, 2));
    fs.renameSync(`${this.memoryPath}.tmp`, this.memoryPath);
  }

  async scanMemory(expectedVersion) {
    const status = await this.status();
    if (!status.connected || status.error || !/^0x[0-9a-f]{4}$/i.test(status.body_version)) return { ok: false, error: status.error || '请先连接相机。' };
    const bodyVersion = status.body_version.toLowerCase();
    if (expectedVersion && expectedVersion.toLowerCase() !== bodyVersion) return { ok: false, error: '机身版本已变化，请刷新后重新扫描。' };
    this.progressPhase = 'scan';
    this.emitProgress({ done: 0, total: (END - START) / BLOCK });
    try {
      let result;
      if (this.mock) {
        for (let step = 1; step <= 20; step++) {
          await new Promise(resolve => setTimeout(resolve, 150));
          this.emitProgress({ done: Math.round((END - START) / BLOCK * step / 20), total: (END - START) / BLOCK });
        }
        const runs = [];
        for (let offset = 0; offset < this.mockRam.length; offset += BLOCK) {
          const block = this.mockRam.subarray(offset, offset + BLOCK);
          const kind = block.every(value => value === 0x55) ? 'free-0x55' : block.every(value => value === 0) ? 'zero'
            : block.subarray(0, 8).toString() === 'LMXTSLOT' ? 'lumixtool' : 'data';
          const previous = runs.at(-1);
          if (previous?.kind === kind) { previous.end = hexAddress(START + offset + BLOCK); previous.kib++; }
          else runs.push({ start: hexAddress(START + offset), end: hexAddress(START + offset + BLOCK), kind, kib: 1 });
        }
        result = { ok: true, start: hexAddress(START), length: END - START, runs };
      } else result = await this.run(['scan']);
      if (!result.ok) return result;
      const map = { scannedAt: new Date().toISOString(), bodyVersion, start: result.start, length: result.length, runs: result.runs };
      this.saveMemoryMap(map);
      return { ok: true, map };
    } finally { this.progressPhase = null; }
  }

  renameSound({ version, index, label } = {}) {
    if (typeof version !== 'string' || !validIndex(index) || typeof label !== 'string' || label.length > 80) return { ok: false, error: '音效名称无效（最多 80 字）。' };
    const sounds = this.loadSounds();
    const saved = sounds[version.toLowerCase()];
    if (!saved) return { ok: false, error: '请先连接并读取音效表。' };
    saved.labels[index] = label.trim();
    this.saveSounds(sounds);
    return { ok: true, labels: saved.labels };
  }

  async testPython(executable) {
    return new Promise(resolve => {
      const child = spawn(executable, ['-c', 'import sys;print(sys.version_info[0])'], { windowsHide: true });
      let output = '';
      const timer = setTimeout(() => { child.kill(); resolve(false); }, 8000);
      child.stdout.on('data', data => { output += data; });
      child.stderr.resume();
      child.on('error', () => { clearTimeout(timer); resolve(false); });
      child.on('close', code => { clearTimeout(timer); resolve(code === 0 && output.trim() === '3'); });
    });
  }

  async findPython() {
    if (this.python) return this.python;
    const candidates = [...new Set([this.loadConfig().python, process.env.LUMIXTOOL_PYTHON, this.bundledPython,
      process.env.S5_PYTHON,
      this.platform === 'win32' && 'C:\\Users\\28985\\.dsh\\dsh-runtimes\\dsh-next-primary-runtime\\dependencies\\python\\python.exe',
      'python3', 'python', 'py'].filter(Boolean))];
    for (const candidate of candidates) {
      if (await this.testPython(candidate)) return (this.python = candidate);
    }
    return null;
  }

  async setPython(executable) {
    if (!await this.testPython(executable)) return { ok: false, error: '所选文件不是可用的 Python 3。请检查路径后重试。' };
    const config = { ...this.loadConfig(), python: executable };
    fs.mkdirSync(path.dirname(this.configPath), { recursive: true });
    fs.writeFileSync(this.configPath, JSON.stringify(config, null, 2));
    this.python = executable;
    return { ok: true, python: executable };
  }

  async environment() {
    return {
      python: this.mock ? (this.mockState.scenario === 'python-missing' ? null : 'Mock · 无需 Python') : await this.findPython(),
      platform: this.platform, mock: this.mock, mockState: this.mock ? { ...this.mockState } : null,
      userData: path.dirname(this.configPath),
    };
  }

  async run(args) {
    const executable = await this.findPython();
    if (!executable) return { connected: false, ok: false, pythonMissing: true, error: '未找到 Python 3，请在设置中选择 Python 可执行文件。' };
    const result = await new Promise((resolve, reject) => {
      const child = spawn(executable, ['-u', this.scriptPath, ...args], { windowsHide: true });
      let stdout = '', stderr = '';
      const outputDecoder = new StringDecoder('utf8');
      const errorDecoder = new StringDecoder('utf8');
      const reader = lineReader(line => {
        const match = /^PROGRESS\s+(\d+)\s+(\d+)$/.exec(line);
        if (match && Number(match[2]) > 0) this.emitProgress({ done: Number(match[1]), total: Number(match[2]) });
      });
      // Writes can legitimately take several minutes; device reads have a deadline.
      const timer = ['status', 'dump'].includes(args[0]) ? setTimeout(() => child.kill(), 20000) : null;
      child.stdout.on('data', data => { stdout += outputDecoder.write(data); reader.write(data); });
      child.stderr.on('data', data => { stderr += errorDecoder.write(data); });
      child.on('error', error => { clearTimeout(timer); reject(error); });
      child.on('close', code => {
        clearTimeout(timer);
        stdout += outputDecoder.end();
        stderr += errorDecoder.end();
        reader.end();
        resolve({ code, stdout, stderr });
      });
    });
    return parseResult(result);
  }

  async status() {
    if (this.mock) {
      const { scenario, custom } = this.mockState;
      if (scenario === 'python-missing') return { connected: false, pythonMissing: true, error: '未找到 Python 3，请在设置中指定路径。' };
      if (scenario === 'disconnected') return { connected: false };
      if (!this.driver.mockStatus().ok) return { connected: false };
      if (scenario === 'error') return { connected: true, error: '模拟 USB 读取失败：设备被其他程序占用。' };
      if (scenario === 'unverified') return { connected: true, model: 'DC-S5', body_version: '0x0280', custom, verified: false, table_problem: null };
      return { connected: true, model: 'DC-S5', body_version: '0x0290', custom, verified: true, table_problem: null };
    }
    if (!await this.findPython()) return { connected: false, pythonMissing: true, error: '未找到 Python 3，请在设置中指定路径。' };
    // The existing backend imports winreg/WinUSB. Do not run it on macOS/Linux.
    if (this.platform !== 'win32') return { connected: false, platformNote: '当前实机连接使用 Windows WinUSB；macOS 开发请启用模拟模式。' };
    return this.run(['status']);
  }

  configureMock(options = {}) {
    if (!this.mock) return { ok: false, error: '模拟模式未启用。' };
    if (['connected', 'disconnected', 'error', 'python-missing', 'region-not-free', 'unverified'].includes(options.scenario)) {
      this.mockState.scenario = options.scenario;
      this.mockState.staleNext = options.scenario === 'region-not-free';
    }
    if (typeof options.failNext === 'boolean') this.mockState.failNext = options.failNext;
    if (DRIVER_SCENARIOS.includes(options.driverScenario)) this.mockState.driverScenario = options.driverScenario;
    if (DRIVER_RESULTS.includes(options.driverResult)) this.mockState.driverResult = options.driverResult;
    return { ok: true, ...this.mockState };
  }

  driverStatus() { return this.driver.status(); }
  installDriver() { return this.driver.change('install'); }
  uninstallDriver(options) { return this.driver.change('uninstall', options); }

  async mockOperation(kind, total) {
    if (this.mockState.scenario === 'unverified') return { ok: false, error: 'unsupported firmware: body version 0x0280 has not been verified (verified: 0x0290); writing is disabled' };
    if (!['connected', 'region-not-free'].includes(this.mockState.scenario)) return { ok: false, error: '模拟设备未就绪，请先连接设备。' };
    const failure = this.mockState.failNext;
    this.mockState.failNext = false;
    for (let step = 1; step <= 20; step++) {
      await new Promise(resolve => setTimeout(resolve, 150));
      this.emitProgress({ done: Math.round(total * step / 20), total });
      if (failure && step === 12) return { ok: false, error: '模拟写入失败：USB 传输超时。请检查连接后重试。' };
    }
    this.mockState.custom = kind === 'apply';
    return { ok: true };
  }

  async apply(payload) {
    // Compatibility IPC uses the same allocator, never a hidden fixed address.
    const result = await this.soundBatch('apply', { ...payload, indices: [1] });
    return result.ok ? { ok: true } : result;
  }

  async restore() {
    if (this.mock) {
      const result = await this.restoreId(1, mockTable[1].hex);
      return result.ok ? { ok: true } : result;
    }
    if (this.platform !== 'win32') return { ok: false, error: '实机恢复需要 Windows WinUSB 环境。' };
    return this.run(['restore']);
  }

  async applySlot(payload) {
    const pcm = pcmBuffer(payload);
    if (!validIndex(payload.index)) throw new Error('音效编号必须为 0–27。');
    const addr = payload.regionAddr;
    if (!Number.isInteger(addr) || addr % BLOCK || addr < START || addr + 16 + pcm.length > END) throw new Error('写入地址必须按 1 KiB 对齐，且完整位于 RAM 暂存区。');
    if (this.mock) {
      if (this.mockState.scenario === 'unverified') return { ok: false, error: 'unsupported firmware: body version 0x0280 has not been verified (verified: 0x0290); writing is disabled' };
      if (this.mockState.staleNext) {
        this.mockState.staleNext = false;
        // Simulate another entry having claimed this span since the last scan.
        const other = (payload.index + 1) % 28;
        this.mockRam.write('LMXTSLOT', addr - START);
        this.mockRam.writeUInt32LE(other, addr - START + 8);
        this.mockRam.writeUInt32LE(1, addr - START + 12);
      }
      const span = this.mockRam.subarray(addr - START, addr - START + 16 + pcm.length);
      // Same rule as s5focus.region_is_free: the 0x8F scratch keeps stale bytes
      // across warm reboots, so only a valid header of another entry blocks a write.
      const headerIndex = span.readUInt32LE(8), headerSamples = span.readUInt32LE(12);
      const foreignHeader = span.subarray(0, 8).toString() === 'LMXTSLOT' && headerIndex < 28 &&
        headerSamples > 0 && headerSamples <= 132300 && headerIndex !== payload.index;
      if (foreignHeader) {
        return { ok: false, error: 'region not free', address: hexAddress(addr), index: payload.index };
      }
      const result = await this.mockOperation('apply', payload.samples);
      if (!result.ok) return result;
      const raw = Buffer.from(this.mockEntries[payload.index].hex, 'hex');
      span.write('LMXTSLOT', 0);
      span.writeUInt32LE(payload.index, 8);
      span.writeUInt32LE(payload.samples, 12);
      pcm.copy(span, 16);
      const virtual = addr + 16 - 0x80000000;
      raw.writeUInt32LE(virtual, 4);
      raw.writeUInt32LE(payload.samples * 2, 0x14);
      this.mockEntries[payload.index] = { ...this.mockEntries[payload.index], addr: hexAddress(virtual), size: payload.samples * 2, hex: raw.toString('hex') };
      this.mockState.custom = true;
      return { ok: true, index: payload.index, entry: raw.toString('hex') };
    }
    if (this.platform !== 'win32') return { ok: false, error: '实机写入需要 Windows WinUSB 环境。' };
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lumixtool-'));
    const filename = path.join(directory, 'audio.pcm');
    try {
      fs.writeFileSync(filename, pcm);
      return await this.run(['apply-slot', String(payload.index), filename, String(payload.samples), hexAddress(addr)]);
    } finally { fs.rmSync(directory, { recursive: true, force: true }); }
  }

  async restoreId(index, hex) {
    if (!validIndex(index) || !validHex(hex) || !isStockAddress(Buffer.from(hex, 'hex').readUInt32LE(4))) {
      return { ok: false, error: '没有可用的原始表项，无法单独恢复（拔电池可恢复）。' };
    }
    if (this.mock) {
      const result = await this.mockOperation('restore', 32);
      if (!result.ok) return result;
      const raw = Buffer.from(hex, 'hex');
      this.mockEntries[index] = { ...this.mockEntries[index], hex,
        addr: `0x${raw.readUInt32LE(4).toString(16).padStart(8, '0').toUpperCase()}`, size: raw.readUInt32LE(0x14) };
      this.mockState.custom = this.mockEntries.some(entry => isScratch(entry.addr));
      return { ok: true, index, entry: hex };
    }
    if (this.platform !== 'win32') return { ok: false, error: '实机恢复需要 Windows WinUSB 环境。' };
    return this.run(['restore-id', String(index), hex]);
  }

  // The IPC caller holds its device lock for this entire loop, including the
  // initial backup and the gaps between entries. Never continue after failure.
  async soundBatch(kind, payload = {}) {
    const succeeded = [];
    let indices = payload.indices;
    try {
      if (kind === 'apply') pcmBuffer(payload);
      if (indices != null && (!Array.isArray(indices) || !indices.length || indices.length > 28 || indices.some(i => !validIndex(i)) || new Set(indices).size !== indices.length)) {
        throw new Error('请选择 0–27 之间不重复的音效编号。');
      }
      if (kind === 'apply' && !indices) throw new Error('请选择要替换的音效。');
      const device = await this.inspect();
      if (!device.connected || device.error || !device.soundTable?.ok) throw new Error(device.error || device.soundTable?.error || '设备未就绪，无法读取音效备份。');
      if (payload.version && payload.version !== device.soundTable.version) throw new Error('机身版本已变化，请刷新后重新操作。');
      const originals = device.soundTable.originals;
      if (kind === 'restore') {
        indices ||= Object.keys(originals).map(Number).filter(validIndex);
        if (!indices.length || indices.some(index => !validHex(originals[index]))) throw new Error('没有可用的原始表项，无法单独恢复（拔电池可恢复）。');
      }
      let map, plan;
      if (kind === 'apply') {
        map = this.memoryMap(device.soundTable.version).map;
        if (!map) {
          const scan = await this.scanMemory(device.soundTable.version);
          if (!scan.ok) return { ...scan, succeeded };
          map = scan.map;
        }
        plan = planAllocation(map, device.soundTable.entries, indices, payload.samples);
        if (!plan.ok) return { ...plan, succeeded };
      }
      const total = kind === 'apply' ? payload.samples : 32;
      for (const [position, index] of indices.entries()) {
        this.batchContext = { index, position: position + 1, count: indices.length, completedUnits: succeeded.length * total };
        this.emitProgress({ done: 0, total });
        let result;
        try {
          result = kind === 'apply' ? await this.applySlot({ ...payload, index, regionAddr: plan.allocations[position].start }) : await this.restoreId(index, originals[index]);
        } catch (error) { result = { ok: false, error: error.message || String(error) }; }
        if (kind === 'apply' && (result.ok || result.error === 'region not free')) {
          const allocation = plan.allocations[position];
          // A refusal means another entry's header sits there; either way the span is LumixTool-owned now.
          // ('data' would not help: since 730faad stale data is allocatable, so the next plan would pick it again.)
          map = markRange(map, allocation.start, allocation.end, 'lumixtool');
          if (!result.ok) result = { ...result, code: 'stale-map', rescan: true,
            error: `目标区域 ${result.address || allocation.address} 已被占用，内存扫描缓存可能已过期；本项未写入，请重新扫描内存后再试。` };
          // Record a successful device write even if saving the local cache fails.
          try { this.saveMemoryMap(map); }
          catch (error) {
            if (result.ok) succeeded.push(index);
            return { ok: false, error: `内存缓存保存失败：${error.message}`, failedIndex: index, succeeded, pending: indices.slice(position + 1) };
          }
        }
        if (!result.ok) return { ...result, failedIndex: index, succeeded, pending: indices.slice(position + 1) };
        succeeded.push(index);
        this.emitProgress({ done: total, total });
      }
      return { ok: true, succeeded };
    } catch (error) { return { ok: false, succeeded, error: error.message || String(error) }; }
    finally { this.batchContext = null; }
  }
}

module.exports = { Runtime, lineReader, parseResult };
