import test from 'node:test';
import assert from 'node:assert/strict';
import { copyOfflineScenes } from '../offline-export.js';
import { framePlan, mixPcmChunk, pcmPeak } from '../render-worker.js';

function scene(channels, sampleRate, title = '测试') {
  return { title, pcm: channels, audioInfo: { sampleRate, length: channels[0].length,
    duration: channels[0].length / sampleRate } };
}

test('CFR rounds up the final frame and leaves complete audio at 48k', () => {
  const result = framePlan(4.82, 30);
  assert.equal(result.frames, 145);
  assert.equal(result.duration, 145 / 30);
  assert.equal(result.samples, 232000);
  assert.ok(result.duration >= 4.82 && result.duration - 4.82 < 1 / 30);
});

test('speech is inserted at absolute audioStart and silent leading/tail samples remain', () => {
  const speech = new Float32Array(24000).fill(.25);
  const input = [scene([speech], 24000)];
  const timeline = [{ audioStart: .35 }];
  const before = mixPcmChunk(input, timeline, 16000, 1000);
  assert.ok(before.subarray(0, 800).every(v => v === 0));
  assert.ok(before.subarray(800, 1000).every(v => v === .25));
  assert.ok(before.subarray(1800, 2000).every(v => v === .25));
  const after = mixPcmChunk(input, timeline, 64750, 100);
  assert.ok(after.subarray(0, 50).every(v => v === .25));
  assert.ok(after.subarray(50, 100).every(v => v === 0));
});

test('24k stereo PCM is resampled without swapping planes or dropping the final source sample', () => {
  const input = [scene([new Float32Array([0, 1, 0, -1]), new Float32Array([1, 0, -1, 0])], 24000)];
  const mixed = mixPcmChunk(input, [{ audioStart: 0 }], 0, 8);
  assert.deepEqual([...mixed.subarray(0, 8)], [0, .5, 1, .5, 0, -.5, -1, -1]);
  assert.deepEqual([...mixed.subarray(8, 16)], [1, .5, 0, -.5, -1, -.5, 0, 0]);
});

test('resampling remains continuous across audio encoder block boundaries', () => {
  const values = Float32Array.from({ length: 1000 }, (_, i) => Math.sin(i * .1));
  const input = [scene([values], 44100)];
  const tl = [{ audioStart: 0 }];
  const full = mixPcmChunk(input, tl, 0, 640);
  const left = mixPcmChunk(input, tl, 0, 113);
  const right = mixPcmChunk(input, tl, 113, 527);
  for (let i = 0; i < 640; i++) assert.ok(Math.abs(full[i] - (i < 113 ? left[i] : right[i - 113])) < 1e-7);
});

test('audio preparation copies sample buffers instead of detaching original narration', async () => {
  const original = new Float32Array([.1, .2, .3]);
  const audio = { duration: 3 / 24000, sampleRate: 24000, length: 3, numberOfChannels: 1, getChannelData: () => original };
  const result = await copyOfflineScenes([{ id: 'a', kind: 'text', title: '保留原件', narration: '原文。', items: [], audio }]);
  assert.notEqual(result.scenes[0].pcm[0].buffer, original.buffer);
  result.scenes[0].pcm[0][0] = .8;
  assert.ok(Math.abs(original[0] - .1) < 1e-6);
  assert.equal(original.byteLength, 12);
  assert.equal(result.transfer[0], result.scenes[0].pcm[0].buffer);
});

test('missing speech never silently becomes an audio-free success, and cancellation is explicit', async () => {
  await assert.rejects(copyOfflineScenes([{ kind: 'text', title: '未配音', narration: '必须保留。', items: [] }]), /还没有配音/u);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(copyOfflineScenes([], { signal: controller.signal }), { name: 'AbortError' });
  assert.throws(() => pcmPeak([scene([new Float32Array([NaN])], 24000)]), /无效采样/u);
});
