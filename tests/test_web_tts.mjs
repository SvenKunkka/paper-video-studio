import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createSpeechService, splitNaturalText } from '../web/tts/core.js';

test('vendored WASM factory provides the native WebGPU entry required by ORT', async () => {
  const { default: factory } = await import('../web/tts/vendor/ort-wasm-simd-threaded.asyncify.mjs');
  const wasmBinary = new Uint8Array(await readFile(new URL('../web/tts/vendor/ort-wasm-simd-threaded.asyncify.wasm', import.meta.url)));
  const runtime = await factory({ wasmBinary, numThreads: 1, print: () => {}, printErr: () => {} });
  assert.equal(typeof runtime.webgpuInit, 'function');
  assert.equal(typeof runtime._OrtInit, 'function');
});

const bufferFactory = options => ({
  ...options,
  duration: options.length / options.sampleRate,
  data: new Float32Array(options.length),
  copyToChannel(samples, channel, offset = 0) { this.data.set(samples, offset); },
});

test('natural segmentation preserves all text, including long unspaced Chinese', () => {
  for (const text of [
    '第一句。第二句，带一个停顿。\n第三句！',
    '没有标点的长中文'.repeat(30),
    'This is an English sentence. Here is another one.\n最后是中文。',
    '# TXT符号保留。**强调**、[链接](x)不会丢失。',
  ]) {
    const chunks = splitNaturalText(text);
    assert.equal(chunks.join('').replace(/\s/gu, ''), text.replace(/\s/gu, ''));
    assert.ok(chunks.every(chunk => Array.from(chunk).length <= 42));
  }
});

test('model is lazy and its loading promise is shared', async () => {
  let loads = 0;
  const service = createSpeechService({ loadRuntime: async report => { loads += 1; report({ stage: 'model', progress: 30 }); return {}; }, createAudioBuffer: bufferFactory });
  assert.equal(loads, 0);
  const [first, second] = await Promise.all([service.loadTTS(), service.loadTTS()]);
  assert.equal(loads, 1);
  assert.equal(first, second);
  assert.equal(await service.loadTTS(), first);
});

test('PCM lengths define cue boundaries and audio length without guessed timing', async () => {
  const spoken = [];
  const service = createSpeechService({
    loadRuntime: async () => ({ generate: async text => {
      spoken.push(text);
      return { data: Float32Array.from({ length: spoken.length * 2400 }, () => 0.25), sampling_rate: 24000 };
    } }), createAudioBuffer: bufferFactory,
  });
  const { audio, cues } = await service.synthesizeScene('第一句。第二句。');
  assert.deepEqual(spoken, ['第一句。', '第二句。']);
  assert.equal(cues[0].start, 0);
  assert.equal(cues[0].end, 0.1);
  assert.equal(cues[1].start, 0.18);
  assert.equal(cues[1].end, 0.38);
  assert.equal(audio.length, 9120);
  assert.equal(audio.duration, 0.38);
  assert.equal(audio.data[0], 0.25);
  assert.equal(audio.data[2400], 0);
  assert.equal(audio.data[4320], 0.25);
});

test('pre-aborted calls never load the model', async () => {
  let loads = 0;
  const service = createSpeechService({ loadRuntime: async () => { loads += 1; return {}; }, createAudioBuffer: bufferFactory });
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(service.loadTTS({ signal: controller.signal }), { name: 'AbortError' });
  await assert.rejects(service.synthesizeScene('文案。', { signal: controller.signal }), { name: 'AbortError' });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(loads, 0);
});

test('a failed model initialization can be retried', async () => {
  let loads = 0;
  const service = createSpeechService({ loadRuntime: async () => { if (++loads === 1) throw new Error('加载失败'); return {}; }, createAudioBuffer: bufferFactory });
  await assert.rejects(service.loadTTS(), /加载失败/);
  await service.loadTTS();
  assert.equal(loads, 2);
});

test('silent output is reported as an error rather than exported silently', async () => {
  const service = createSpeechService({ loadRuntime: async () => ({ generate: async () => ({ data: new Float32Array(2400), sampling_rate: 24000 }) }), createAudioBuffer: bufferFactory });
  await assert.rejects(service.synthesizeScene('文案。'), /没有生成有效声音/);
});

test('non-finite output is rejected without replacing samples with silence', async () => {
  const pcm = new Float32Array(2400).fill(0.2);
  pcm[100] = NaN;
  pcm[101] = Infinity;
  let created = false;
  const service = createSpeechService({
    loadRuntime: async () => ({ generate: async () => ({ data: pcm, sampling_rate: 24000 }) }),
    createAudioBuffer: options => { created = true; return bufferFactory(options); },
  });
  await assert.rejects(service.synthesizeScene('文案。'), /无效音频样本/);
  assert.equal(created, false);
  assert.ok(Number.isNaN(pcm[100]));
  assert.equal(pcm[101], Infinity);
});

test('abort while inference runs rejects and discards its result', async () => {
  let finish;
  let started;
  const inferenceStarted = new Promise(resolve => { started = resolve; });
  const service = createSpeechService({
    loadRuntime: async () => ({ generate: () => { started(); return new Promise(resolve => { finish = resolve; }); } }),
    createAudioBuffer: bufferFactory,
  });
  const controller = new AbortController();
  const result = service.synthesizeScene('文案。', { signal: controller.signal });
  await inferenceStarted;
  controller.abort();
  await assert.rejects(result, { name: 'AbortError' });
  finish({ data: new Float32Array(2400).fill(0.1), sampling_rate: 24000 });
  await new Promise(resolve => setTimeout(resolve, 0));
});
