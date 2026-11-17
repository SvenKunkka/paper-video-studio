/**
 * Deterministic paper-film sound design. No playback clock, device, network or
 * mutable DSP state is involved, so preview and offline chunks use the same PCM.
 * offset and length in makePaperPcm are global sample counts, not seconds.
 */

const TAU = Math.PI * 2;
const MAX_PEAK = .48;

export const PAPER_SOUND_PHASES = Object.freeze([
  Object.freeze({ start: 0, end: .6, label: '纸张撕裂' }),
  Object.freeze({ start: .6, end: 2.6, label: '纸带摩擦与落下' }),
  Object.freeze({ start: 2.6, end: 5.1, label: '碎纸机低鸣与切纸' }),
  Object.freeze({ start: 5.1, end: 8, label: '纸条归位轻响' }),
]);

function hashNoise(index, seed) {
  let value = Math.imul((index | 0) ^ seed, 0x45d9f3b);
  value = Math.imul(value ^ (value >>> 16), 0x45d9f3b);
  value ^= value >>> 16;
  return (value >>> 0) / 0xffffffff * 2 - 1;
}

function smoothNoise(seconds, frequency, seed) {
  const position = seconds * frequency;
  const index = Math.floor(position);
  const fraction = position - index;
  const blend = fraction * fraction * (3 - 2 * fraction);
  const a = hashNoise(index, seed);
  return a + (hashNoise(index + 1, seed) - a) * blend;
}

function ramp(value) {
  const x = Math.max(0, Math.min(1, value));
  return x * x * (3 - 2 * x);
}

function windowAt(phase, start, end, attack = .06, release = .1) {
  if (phase <= start || phase >= end) return 0;
  return ramp((phase - start) / attack) * ramp((end - phase) / release);
}

function sampleRateValue(sampleRate) {
  if (!Number.isSafeInteger(sampleRate) || sampleRate <= 0) {
    throw new RangeError('纸张音效采样率必须是正整数。');
  }
  return sampleRate;
}

// Phase positions stretch with each scene; carrier frequencies stay in Hz.
function synthSample(localSeconds, duration, sampleRate) {
  if (localSeconds < 0 || localSeconds >= duration || duration === 0) return 0;
  const phase = localSeconds * 8 / duration;
  const nyquistSafe = sampleRate * .38;
  const noise = (frequency, seed) => smoothNoise(localSeconds, Math.min(frequency, nyquistSafe), seed);
  const tone = (frequency, time = localSeconds) => Math.sin(TAU * Math.min(frequency, nyquistSafe) * time);
  let value = 0;

  if (phase < .6) {
    // Short rough tears, with a soft air movement underneath.
    const gate = windowAt(phase, 0, .6, .025, .1);
    const burst = .28 + .72 * Math.pow(Math.max(0, Math.sin(TAU * phase * 9)), 3);
    value += gate * burst * (.125 * noise(1250, 0x71a9) + .055 * noise(480, 0xa134));
    value += gate * .023 * noise(160, 0x1721);
  }

  if (phase > .6 && phase < 2.6) {
    // Falling ribbons: broad friction plus six rounded, low paper impacts.
    const gate = windowAt(phase, .6, 2.6, .12, .16);
    const flutter = .65 + .35 * tone(7.5);
    value += gate * flutter * (.045 * noise(680, 0x32c7) + .027 * noise(155, 0x4553));
    for (const impact of [.86, 1.18, 1.51, 1.86, 2.2, 2.47]) {
      const delta = phase - impact;
      if (delta >= 0 && delta < .17) {
        const seconds = delta * duration / 8;
        value += gate * .052 * ramp(delta / .006) * Math.exp(-delta / .044)
          * (tone(150, seconds) + .28 * noise(450, 0x63f1));
      }
    }
  }

  if (phase > 2.6 && phase < 5.1) {
    // Low motor harmonics and restrained cutter/feeding texture; no sharp buzz.
    const gate = windowAt(phase, 2.6, 5.1, .16, .14);
    const feed = .82 + .18 * tone(18);
    value += gate * feed * (.055 * tone(63) + .024 * tone(126) + .01 * tone(210)
      + .035 * noise(260, 0x83d5) + .009 * noise(1000, 0x1907));
  }

  if (phase > 5.1 && phase < 8) {
    // Twenty-five softly damped landings, following the reassembly wave.
    const gate = windowAt(phase, 5.1, 8, .06, .16);
    value += gate * .012 * noise(310, 0x25a3);
    const approximate = Math.round((phase - 5.24) / (2.4 / 24));
    for (let i = Math.max(0, approximate - 1); i <= Math.min(24, approximate + 1); i++) {
      const landing = 5.24 + i * (2.4 / 24) + .012 * hashNoise(i, 0x9571);
      const delta = phase - landing;
      if (delta >= 0 && delta < .09) {
        const seconds = delta * duration / 8;
        const envelope = ramp(delta / .003) * Math.exp(-delta / .019);
        value += gate * .115 * envelope * (tone(590 + i % 5 * 43, seconds)
          + .26 * noise(850, 0xb371 + i));
      }
    }
  }

  // Avoid discontinuities when adjacent scenes restart the film.
  return value * ramp(localSeconds / .004) * ramp((duration - localSeconds) / .009);
}

/** Sample the eight-second paper score stretched to a scene's actual duration. */
export function paperSoundSample(localSeconds, sceneDuration, sampleRate = 48000) {
  sampleRateValue(sampleRate);
  if (!Number.isFinite(localSeconds) || !Number.isFinite(sceneDuration) || sceneDuration < 0) {
    throw new RangeError('纸张音效的时间和场景时长必须有效，时长不能为负数。');
  }
  return synthSample(localSeconds, sceneDuration, sampleRate);
}

/**
 * Render a mono PCM slice of the global scene timeline. Defaults to all remaining
 * samples through the final scene's end. Explicit lengths preserve silent gaps
 * and padded tails, which makes this suitable for fixed-size encoder chunks.
 */
export function makePaperPcm(timelineScenes, { sampleRate = 48000, offset = 0, length, level = 1 } = {}) {
  sampleRateValue(sampleRate);
  const input = Array.isArray(timelineScenes) ? timelineScenes : timelineScenes?.scenes;
  if (!Array.isArray(input)) throw new TypeError('纸张音效需要有效的场景时间线。');
  if (!Number.isSafeInteger(offset) || offset < 0) throw new RangeError('音效起点必须是非负整数样本数。');
  if (!Number.isFinite(level) || level < 0) throw new RangeError('音效音量必须是非负有限数值。');

  let end = 0;
  const scenes = input.map(scene => {
    const { start, duration } = scene ?? {};
    if (!Number.isFinite(start) || start < 0 || !Number.isFinite(duration) || duration < 0
      || !Number.isFinite(start + duration)) {
      throw new RangeError('纸张音效场景的起点和时长必须是非负有限秒数。');
    }
    end = Math.max(end, start + duration);
    return { start, duration };
  });

  const count = length ?? Math.max(0, Math.ceil(end * sampleRate) - offset);
  if (!Number.isSafeInteger(count) || count < 0 || !Number.isSafeInteger(offset + count)) {
    throw new RangeError('音效长度必须是非负整数样本数。');
  }
  const output = new Float32Array(count);
  if (level === 0 || count === 0) return output;

  for (const scene of scenes) {
    if (scene.duration === 0) continue;
    const first = Math.max(offset, Math.ceil(scene.start * sampleRate));
    const last = Math.min(offset + count, Math.ceil((scene.start + scene.duration) * sampleRate));
    for (let index = first; index < last; index++) {
      // Absolute integer index ensures that split and full renders are identical.
      const local = index / sampleRate - scene.start;
      output[index - offset] += synthSample(local, scene.duration, sampleRate);
    }
  }
  for (let i = 0; i < count; i++) {
    output[i] = Math.max(-MAX_PEAK, Math.min(MAX_PEAK, output[i] * level));
  }
  return output;
}
