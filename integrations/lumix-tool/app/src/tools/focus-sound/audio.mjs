export const RATE = 44100;
export const MAX_SECONDS = 3;

// Preserve the original conversion: average every input channel, resample with
// Web Audio, trim to three seconds, then quantize explicitly to little-endian s16.
export async function decodeAudio(bytes, filename, audioApi = globalThis) {
  let decoder;
  try {
    const data = bytes instanceof ArrayBuffer ? bytes.slice(0) : new Uint8Array(bytes).buffer;
    decoder = new audioApi.AudioContext();
    const decoded = await decoder.decodeAudioData(data);
    if (!Number.isFinite(decoded.duration) || decoded.duration <= 0) throw new Error('音频为空，请选择有声音的文件。');
    const duration = Math.min(MAX_SECONDS, decoded.duration);
    const frames = Math.max(1, Math.floor(duration * RATE));
    const offline = new audioApi.OfflineAudioContext(1, frames, RATE);
    const inputFrames = Math.min(decoded.length, Math.ceil(duration * decoded.sampleRate));
    const mono = offline.createBuffer(1, inputFrames, decoded.sampleRate);
    const target = mono.getChannelData(0);
    for (let channel = 0; channel < decoded.numberOfChannels; channel++) {
      const source = decoded.getChannelData(channel);
      for (let index = 0; index < target.length; index++) target[index] += source[index] / decoded.numberOfChannels;
    }
    const source = offline.createBufferSource();
    source.buffer = mono;
    source.connect(offline.destination);
    source.start(0, 0, duration);
    const buffer = await offline.startRendering();
    const samples = buffer.getChannelData(0);
    const pcm = new ArrayBuffer(samples.length * 2);
    const view = new DataView(pcm);
    for (let index = 0; index < samples.length; index++) {
      const value = Math.max(-1, Math.min(1, samples[index]));
      const quantized = Math.round(value * (value < 0 ? 32768 : 32767));
      view.setInt16(index * 2, quantized, true);
      // Preview and waveform use the quantized audio that is actually written.
      samples[index] = quantized / 32768;
    }
    return { pcm, buffer, filename, originalDuration: decoded.duration, channels: decoded.numberOfChannels, samples: frames, duration: frames / RATE };
  } finally {
    if (decoder) await decoder.close().catch(() => {});
  }
}
