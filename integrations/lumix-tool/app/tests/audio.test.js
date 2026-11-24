const { test } = require('node:test');
const assert = require('node:assert/strict');

function audioFixture({ duration = 4.25, fail = false } = {}) {
  const channels = [new Float32Array(204000).fill(.75), new Float32Array(204000).fill(-.25), new Float32Array(204000).fill(.25)];
  const captured = {};
  class AudioContext {
    async decodeAudioData() {
      if (fail) throw new Error('Unsupported audio format');
      return { duration, length: 204000, sampleRate: 48000, numberOfChannels: 3, getChannelData: index => channels[index] };
    }
    async close() { captured.closed = true; }
  }
  class OfflineAudioContext {
    constructor(channelCount, frames, rate) { Object.assign(captured, { channelCount, frames, rate }); }
    createBuffer(channelCount, frames, rate) {
      const mono = new Float32Array(frames);
      Object.assign(captured, { inputFrames: frames, inputRate: rate, mono });
      return { getChannelData: () => mono };
    }
    createBufferSource() { return { connect() {}, start: (...args) => { captured.start = args; } }; }
    async startRendering() {
      const output = new Float32Array(captured.frames);
      output.set([-2, -1, -.5, 0, .5, 1, 2]);
      return { getChannelData: () => output, duration: captured.frames / captured.rate };
    }
  }
  return { captured, api: { AudioContext, OfflineAudioContext } };
}

test('conversion preserves real duration, averages every channel, and caps 44.1 kHz mono output at 3 seconds', async () => {
  const { decodeAudio } = await import('../src/tools/focus-sound/audio.mjs');
  const { api, captured } = audioFixture();
  const audio = await decodeAudio(new Uint8Array([1, 2, 3]), 'long.wav', api);
  assert.equal(audio.originalDuration, 4.25);
  assert.equal(audio.duration, 3);
  assert.equal(audio.channels, 3);
  assert.equal(audio.samples, 132300);
  assert.equal(audio.pcm.byteLength, 264600);
  assert.equal(captured.channelCount, 1);
  assert.equal(captured.rate, 44100);
  assert.equal(captured.inputFrames, 144000);
  assert.equal(captured.inputRate, 48000);
  assert.ok(captured.mono.every(sample => Math.abs(sample - .25) < 1e-6));
  assert.deepEqual(captured.start, [0, 0, 3]);
  assert.equal(captured.closed, true);
});

test('PCM clips to signed 16-bit little endian and preview contains the quantized payload', async () => {
  const { decodeAudio } = await import('../src/tools/focus-sound/audio.mjs');
  const { api } = audioFixture({ duration: .5 });
  const audio = await decodeAudio(new ArrayBuffer(8), 'short.wav', api);
  assert.equal(audio.samples, 22050);
  assert.equal(audio.duration, .5);
  assert.deepEqual([...new Uint8Array(audio.pcm).slice(0, 14)], [0, 128, 0, 128, 0, 192, 0, 0, 0, 64, 255, 127, 255, 127]);
  const view = new DataView(audio.pcm);
  for (let index = 0; index < 7; index++) assert.equal(audio.buffer.getChannelData(0)[index], view.getInt16(index * 2, true) / 32768);
});

test('decoder is closed for unsupported or empty audio and errors remain actionable', async () => {
  const { decodeAudio } = await import('../src/tools/focus-sound/audio.mjs');
  const broken = audioFixture({ fail: true });
  await assert.rejects(decodeAudio(new ArrayBuffer(1), 'bad.wav', broken.api), /Unsupported audio format/);
  assert.equal(broken.captured.closed, true);
  const empty = audioFixture({ duration: 0 });
  await assert.rejects(decodeAudio(new ArrayBuffer(1), 'empty.wav', empty.api), /音频为空/);
  assert.equal(empty.captured.closed, true);
});
