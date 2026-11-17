import test from 'node:test';
import assert from 'node:assert/strict';

// The public site is plain ES modules and intentionally needs no Node package metadata.
const { estimateTimeline, makeSrt, exportRealtimeVideo: exportVideo } = await import('../engine.js');

test('audio length controls duration and preserves its complete final tail', () => {
  const buffer = { duration: 5.25 };
  const timeline = estimateTimeline([{ id: 'one', kind: 'text', title: '标题', narration: '完整旁白。', items: [], audio: buffer, duration: 2 }]);
  assert.equal(timeline.duration, 6.25);
  assert.equal(timeline.scenes[0].audioStart, .35);
  assert.equal(timeline.scenes[0].audioEnd, 5.6);
  assert.ok(Math.abs(timeline.scenes[0].end - timeline.scenes[0].audioEnd - .65) < 1e-9);
  assert.equal(timeline.cues[0].text, '完整旁白。');
});

test('measured phrase cues are shifted by scene and audio offsets, without character guessing', () => {
  const timeline = estimateTimeline([
    { id: 'image', kind: 'image', title: '图片', narration: '', items: [] },
    { id: 'voice', kind: 'text', title: '说明', narration: '第一句。第二句。', audio: { duration: 4 },
      cues: [{ start: 0, end: 1.7, text: '第一句。' }, { start: 2, end: 4, text: '第二句。' }] },
  ]);
  assert.equal(timeline.scenes[0].duration, 3);
  assert.equal(timeline.cues[0].start, 3.35);
  assert.equal(timeline.cues[1].start, 5.35);
  assert.equal(timeline.cues[1].end, 7.35);
});

test('stale or out-of-bounds captions are rejected instead of pairing with new audio', () => {
  const scene = { kind: 'text', title: '说明', narration: '新的内容。', audio: { duration: 1 } };
  assert.throws(() => estimateTimeline([{ ...scene, cues: [{ start: 0, end: 1, text: '旧内容。' }] }]), /字幕与旁白原文不一致/u);
  assert.throws(() => estimateTimeline([{ ...scene, cues: [{ start: 0, end: 2, text: '新的内容。' }] }]), /超出配音范围/u);
});

test('SRT keeps every cue and formats hours and milliseconds', () => {
  const result = makeSrt([{ start: .35, end: 1.625, text: '你好。' }, { start: 3601, end: 3602.01, text: '完整保留。' }]);
  assert.match(result, /00:00:00,350 --> 00:00:01,625\n你好。/u);
  assert.match(result, /01:00:01,000 --> 01:00:02,010\n完整保留。/u);
  assert.throws(() => makeSrt([{ start: 2, end: 1, text: '无效' }]), /字幕时间无效/u);
});

test('effects are prepared before the shared origin and delayed recorder events never move it', async () => {
  const names = ['MediaRecorder', 'MediaStream', 'AudioContext', 'requestAnimationFrame', 'cancelAnimationFrame', 'document'];
  const saved = new Map(names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]));
  let clock = 0, stoppedAt = 0, startEventAt = 0, recorderStartedAt = 0;
  const sourceStarts = [];
  const track = kind => ({ kind, stop() {}, requestFrame() {} });
  const audioTrack = track('audio'), videoTrack = track('video');
  class Stream {
    constructor(tracks) { this.tracks = tracks; }
    getTracks() { return this.tracks; }
    getVideoTracks() { return this.tracks.filter(t => t.kind === 'video'); }
    getAudioTracks() { return this.tracks.filter(t => t.kind === 'audio'); }
  }
  class Context extends EventTarget {
    state = 'running'; sampleRate = 48000;
    get currentTime() { return clock; }
    resume() { return Promise.resolve(); }
    close() { this.state = 'closed'; return Promise.resolve(); }
    createGain() { return { gain: { value: 1 }, connect() {}, disconnect() {} }; }
    createMediaStreamDestination() { return { stream: new Stream([audioTrack]), disconnect() {} }; }
    createBuffer(channels, length, rate) {
      return { duration: length / rate, copyToChannel() { clock += .75; } };
    }
    createBufferSource() {
      return { connect() {}, disconnect() {}, stop() {}, start(time) { sourceStarts.push(time); } };
    }
  }
  class Recorder {
    static isTypeSupported(type) { return type.startsWith('video/mp4'); }
    state = 'inactive'; mimeType = 'video/mp4';
    start() {
      this.state = 'recording';
      recorderStartedAt = clock;
      // Reproduce the observed browser case: capture has already started, but
      // the asynchronous notification arrives 1.2 seconds later.
      setImmediate(() => { clock = recorderStartedAt + 1.2; startEventAt = clock; this.onstart(); });
    }
    stop() {
      if (this.state === 'inactive') return;
      this.state = 'inactive'; stoppedAt = clock;
      setImmediate(() => {
        this.ondataavailable({ data: new Blob(['encoded'.repeat(80)], { type: this.mimeType }) });
        this.onstop();
      });
    }
  }
  const methods = ['save', 'restore', 'setTransform', 'fillRect', 'translate', 'scale', 'beginPath', 'moveTo', 'lineTo', 'stroke', 'rect', 'clip', 'fillText', 'strokeRect'];
  const ctx = Object.fromEntries(methods.map(name => [name, () => {}]));
  ctx.measureText = text => ({ width: [...text].length * 20 });
  const canvas = { width: 360, height: 640, getContext: () => ctx, captureStream: () => new Stream([videoTrack]) };
  try {
    Object.assign(globalThis, { MediaRecorder: Recorder, MediaStream: Stream, AudioContext: Context,
      requestAnimationFrame(callback) { return setImmediate(() => { clock += .05; callback(); }); },
      cancelAnimationFrame(handle) { clearImmediate(handle); }, document: undefined });
    const result = await exportVideo({ canvas, scenes: [{ id: 'a', kind: 'text', title: '录制时钟', narration: '完整旁白。', items: [],
      audio: { duration: 2, numberOfChannels: 1, getChannelData: () => new Float32Array([.2, -.2]) } }],
      settings: { width: 360, height: 640, fps: 30, paperSound: true } });
    assert.equal(recorderStartedAt, .75);
    assert.equal(startEventAt, recorderStartedAt + 1.2);
    assert.deepEqual(sourceStarts, [.75, 1.1, .75]);
    assert.ok(stoppedAt >= recorderStartedAt + 3 && stoppedAt < recorderStartedAt + 3.15, `stop=${stoppedAt}`);
    assert.equal(result.plannedDuration, 3);
    assert.equal(result.duration, stoppedAt - recorderStartedAt);
    assert.equal(result.durationSource, 'recording-audio-clock');
    assert.ok(Math.abs(result.timing.startEventDelay - 1.2) < 1e-10);
    assert.equal(result.extension, 'mp4');
  } finally {
    for (const [name, descriptor] of saved) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
});
