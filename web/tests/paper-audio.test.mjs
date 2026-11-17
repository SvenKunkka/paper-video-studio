import test from 'node:test';
import assert from 'node:assert/strict';
import { paperSoundSample, makePaperPcm, PAPER_SOUND_PHASES } from '../paper-audio.js';

function rms(data) {
  return Math.sqrt(data.reduce((sum, sample) => sum + sample * sample, 0) / data.length);
}

test('full mono timeline preserves exact duration, silent gaps and padded tails', () => {
  const scenes = [{ start: .125, duration: 2 }, { start: 2.375, duration: 1.125 }];
  const pcm = makePaperPcm(scenes, { sampleRate: 24000 });
  assert.equal(pcm.length, 84000);
  assert.ok(pcm.subarray(0, 3000).every(value => value === 0));
  assert.ok(pcm.subarray(51000, 57000).every(value => value === 0));
  const tail = makePaperPcm(scenes, { sampleRate: 24000, offset: 84000, length: 1000 });
  assert.equal(tail.length, 1000);
  assert.ok(tail.every(value => value === 0));
});

test('encoder chunks are bit-identical to a full render across scene and block boundaries', () => {
  const scenes = [{ start: .0037, duration: .413 }, { start: .4167, duration: .757 }];
  const whole = makePaperPcm(scenes, { sampleRate: 16000 });
  const combined = new Float32Array(whole.length);
  for (let offset = 0; offset < whole.length; offset += 997) {
    combined.set(makePaperPcm({ scenes }, { sampleRate: 16000, offset,
      length: Math.min(997, whole.length - offset) }), offset);
  }
  assert.deepEqual(combined, whole);
});

test('each paper phase produces finite, audible but restrained sound', () => {
  const rate = 24000;
  const pcm = makePaperPcm([{ start: 0, duration: 8 }], { sampleRate: rate });
  const values = PAPER_SOUND_PHASES.map(({ start, end }) => rms(pcm.subarray(Math.ceil(start * rate), Math.ceil(end * rate))));
  assert.equal(values.length, 4);
  for (const value of values) assert.ok(value > .004 && value < .10, `phase RMS=${value}`);
  assert.ok(pcm.every(value => Number.isFinite(value) && Math.abs(value) <= .25));
  assert.ok(values[2] > values[3], 'motor is sustained while reassembly has separated clicks');
});

test('motor concentrates energy in low frequencies while tearing stays rougher', () => {
  const rate = 16000;
  const pcm = makePaperPcm([{ start: 0, duration: 8 }], { sampleRate: rate });
  const differences = (start, end) => {
    let difference = 0, power = 0;
    for (let i = start * rate + 1; i < end * rate; i++) {
      difference += (pcm[i] - pcm[i - 1]) ** 2;
      power += pcm[i] ** 2;
    }
    return difference / power;
  };
  assert.ok(differences(.05, .5) > differences(2.9, 4.8) * 2);
});

test('score transitions line up with film tear, cascade, cutting and rebuild boundaries', () => {
  assert.deepEqual(PAPER_SOUND_PHASES.map(({ start, end }) => [start, end]),
    [[0, .6], [.6, 2.6], [2.6, 5.1], [5.1, 8]]);
  // Each stage fades its own texture to zero at the exact cut: motor must not
  // leak into the reassembly shot, nor can reassembly clicks precede its cut.
  for (const boundary of [.6, 2.6, 5.1]) {
    assert.ok(Math.abs(paperSoundSample(boundary, 8)) < 1e-12);
    assert.ok(Math.abs(paperSoundSample(boundary - 1 / 48000, 8)) < .00001);
    assert.ok(Math.abs(paperSoundSample(boundary + 1 / 48000, 8)) < .00001);
  }
});

test('scene start/end are smooth, repeated calls are deterministic and outside times are silent', () => {
  for (const duration of [.3, 8, 17]) {
    assert.equal(paperSoundSample(-.1, duration), 0);
    assert.equal(paperSoundSample(0, duration), 0);
    assert.equal(paperSoundSample(duration, duration), 0);
    assert.equal(paperSoundSample(duration + .1, duration), 0);
    assert.ok(Math.abs(paperSoundSample(duration - 1 / 48000, duration)) < .00001);
    for (const fraction of [.03, .18, .45, .7, .9]) {
      assert.equal(paperSoundSample(duration * fraction, duration), paperSoundSample(duration * fraction, duration));
    }
  }
  assert.equal(paperSoundSample(0, 0), 0);
});

test('mix level zero is silent and overlapping loud scenes have a safe peak', () => {
  const scenes = Array.from({ length: 12 }, () => ({ start: 0, duration: .6 }));
  const silent = makePaperPcm(scenes, { sampleRate: 16000, level: 0 });
  assert.ok(silent.every(value => value === 0));
  const loud = makePaperPcm(scenes, { sampleRate: 16000, level: 5 });
  assert.ok(loud.every(value => Number.isFinite(value) && Math.abs(value) <= .480001));
  assert.ok(rms(loud) > .02);
});

test('invalid timestamps, lengths and non-finite controls fail explicitly', () => {
  assert.throws(() => paperSoundSample(NaN, 8), /时间/u);
  assert.throws(() => paperSoundSample(0, -1), /时长/u);
  assert.throws(() => paperSoundSample(0, 8, 0), /采样率/u);
  assert.throws(() => makePaperPcm([{ start: 0, duration: Infinity }]), /时长/u);
  assert.throws(() => makePaperPcm([], { offset: .5 }), /样本/u);
  assert.throws(() => makePaperPcm([], { length: -1 }), /长度/u);
  assert.throws(() => makePaperPcm([], { level: NaN }), /音量/u);
  assert.equal(makePaperPcm([]).length, 0);
});
