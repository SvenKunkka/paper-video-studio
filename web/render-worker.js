/** Fixed-timestamp worker exporter. Mediabunny API pinned to 1.66.0. */
import { Output, BufferTarget, Mp4OutputFormat, WebMOutputFormat, CanvasSource, AudioSampleSource,
  AudioSample, Quality, canEncodeVideo, canEncodeAudio, Input, BufferSource, MP4, WEBM } from 'mediabunny';
import { drawFrame, estimateTimeline } from './engine.js';
import { makePaperPcm } from './paper-audio.js';

const RATE = 48000;
const CHANNELS = 2;
const AUDIO_BLOCK = 4096;

function unavailable(message) {
  const error = new Error(message); error.name = 'OfflineExportUnavailableError'; error.code = 'OFFLINE_UNAVAILABLE'; return error;
}

export function framePlan(duration, fps) {
  if (!(Number.isFinite(duration) && duration > 0 && Number.isInteger(fps) && fps >= 1 && fps <= 60)) throw new Error('离线时长或帧率无效。');
  const frames = Math.ceil(duration * fps - 1e-8);
  return { frames, duration: frames / fps, samples: Math.round(frames / fps * RATE) };
}

export function pcmPeak(scenes) {
  let peak = 0;
  for (const scene of scenes) for (const channel of scene.pcm ?? []) {
    for (let i = 0; i < channel.length; i++) {
      if (!Number.isFinite(channel[i])) throw new Error(`分镜“${scene.title}”配音中含无效采样，请重新生成。`);
      peak = Math.max(peak, Math.abs(channel[i]));
    }
  }
  return peak;
}

/** Planar stereo float PCM, resampled to 48k without a running AudioContext. */
export function mixPcmChunk(scenes, timeline, offset, length, gain = 1) {
  const data = new Float32Array(length * CHANNELS);
  const begin = offset / RATE, end = (offset + length) / RATE;
  for (let si = 0; si < scenes.length; si++) {
    const source = scenes[si];
    if (!source.pcm?.length || !source.audioInfo) continue;
    const start = timeline[si].audioStart;
    const sourceEnd = start + source.audioInfo.length / source.audioInfo.sampleRate;
    if (sourceEnd <= begin || start >= end) continue;
    const first = Math.max(0, Math.ceil(start * RATE - offset - 1e-7));
    const last = Math.min(length, Math.ceil(sourceEnd * RATE - offset - 1e-7));
    const channels = source.pcm;
    for (let i = first; i < last; i++) {
      const position = Math.max(0, ((offset + i) / RATE - start) * source.audioInfo.sampleRate);
      const left = Math.min(source.audioInfo.length - 1, Math.floor(position));
      const right = Math.min(source.audioInfo.length - 1, left + 1);
      const fraction = position - left;
      for (let ch = 0; ch < CHANNELS; ch++) {
        let value = 0;
        if (channels.length <= 2) {
          const values = channels[Math.min(ch, channels.length - 1)];
          value = values[left] + (values[right] - values[left]) * fraction;
        } else {
          // Retain all source channels when speech imports contain multichannel audio.
          for (const values of channels) value += (values[left] + (values[right] - values[left]) * fraction) / channels.length;
        }
        data[ch * length + i] += value * gain;
      }
    }
  }
  return data;
}

async function chooseEncoding(settings) {
  if (typeof globalThis.VideoEncoder !== 'function' || typeof globalThis.AudioEncoder !== 'function') {
    throw unavailable('此浏览器的工作线程不支持 WebCodecs，请选择兼容模式。');
  }
  const videoOptions = { width: settings.width, height: settings.height, frameRate: settings.fps,
    quality: new Quality({ bitrate: Math.max(750000, Math.min(24000000, settings.width * settings.height * settings.fps * .12)) }) };
  const audioOptions = { numberOfChannels: CHANNELS, sampleRate: RATE, quality: new Quality({ bitrate: 192000 }) };
  for (const pair of [{ video: 'avc', audio: 'aac', extension: 'mp4' },
    { video: 'vp9', audio: 'opus', extension: 'webm' }, { video: 'vp8', audio: 'opus', extension: 'webm' }]) {
    const [video, audio] = await Promise.all([canEncodeVideo(pair.video, videoOptions), canEncodeAudio(pair.audio, audioOptions)]);
    if (video && audio) return { ...pair, videoOptions, audioOptions };
  }
  throw unavailable('没有可用的离线视频与音频编码器，请选择兼容模式或更换浏览器。');
}

async function inspectEncoded(buffer, expected, fps) {
  const input = new Input({ source: new BufferSource(buffer), formats: [MP4, WEBM] });
  try {
    const [videos, audios] = await Promise.all([input.getVideoTracks(), input.getAudioTracks()]);
    if (videos.length !== 1 || audios.length !== 1) throw new Error('离线成片缺少画面或声音轨道。');
    const duration = await input.computeDuration();
    // Audio codecs may retain one final packet of padding; never call a large discrepancy complete.
    if (!Number.isFinite(duration) || duration < expected - .025 || duration > expected + Math.max(.12, 2 / fps)) {
      throw new Error(`离线成片时长异常：应为 ${expected.toFixed(3)} 秒，实际 ${Number(duration).toFixed(3)} 秒。`);
    }
    return duration;
  } finally { input.dispose(); }
}

export async function renderOffline({ scenes, settings: userSettings = {} }, progress = () => {}) {
  const settings = { width: 1080, height: 1920, fps: 30, paper: '#eeece7', ink: '#181716', accent: '#ac1210', ...userSettings };
  for (const key of ['width', 'height', 'fps']) settings[key] = Number(settings[key]);
  settings.silent = userSettings.silent === true;
  if (typeof OffscreenCanvas !== 'function') throw unavailable('此浏览器不支持工作线程画布，请选择兼容模式。');
  progress({ progress: 0, elapsed: 0, duration: 0, phase: 'prepare', message: '正在准备画面与字体。', renderMode: 'offline' });
  // These scenes use installed system fonts. In a dedicated worker, waiting on
  // FontFaceSet.ready before the first canvas draw can stay pending forever;
  // there is no document layout cycle to unblock it. Explicit web fonts, if
  // introduced later, must be loaded individually with FontFace.load().
  const viewScenes = scenes.map(scene => ({ ...scene, audio: scene.audioInfo ? { duration: scene.audioInfo.duration } : null }));
  const timeline = estimateTimeline(viewScenes, settings);
  if (!timeline.scenes.length) throw new Error('没有可渲染的场景。');
  const plan = framePlan(timeline.duration, Number(settings.fps));
  const canvas = new OffscreenCanvas(Number(settings.width), Number(settings.height));
  // Validate stage content and every complete caption before starting encoders.
  for (const scene of timeline.scenes) {
    drawFrame(canvas, { scenes: viewScenes, settings }, scene.start + .31);
    for (const cue of scene.captionCues) drawFrame(canvas, { scenes: viewScenes, settings }, scene.start + (cue.start + cue.end) / 2);
  }
  progress({ progress: 0, elapsed: 0, duration: plan.duration, phase: 'prepare', message: '正在检查浏览器的视频编码能力。', renderMode: 'offline' });
  const encoding = await chooseEncoding(settings);
  const target = new BufferTarget();
  const output = new Output({ target, format: encoding.extension === 'mp4' ? new Mp4OutputFormat({ fastStart: 'in-memory' }) : new WebMOutputFormat() });
  const video = new CanvasSource(canvas, { codec: encoding.video, quality: encoding.videoOptions.quality,
    latencyMode: 'quality', keyFrameInterval: 2 });
  const audio = new AudioSampleSource({ codec: encoding.audio, quality: encoding.audioOptions.quality });
  output.addVideoTrack(video, { frameRate: settings.fps });
  output.addAudioTrack(audio, { languageCode: 'zho' });
  let done = false;
  try {
    const peak = settings.silent ? 0 : pcmPeak(scenes);
    const gain = peak > .92 ? .92 / peak : 1;
    progress({ progress: 0, elapsed: 0, duration: plan.duration, phase: 'prepare', message: '正在准备视频文件。', renderMode: 'offline' });
    await output.start();
    let audioOffset = 0;
    const progressStep = Math.max(1, Math.ceil(plan.frames / 200));
    for (let frame = 0; frame < plan.frames; frame++) {
      const audioTarget = Math.min(plan.samples, Math.ceil((frame + 1) / settings.fps * RATE));
      while (audioOffset < audioTarget) {
        const length = Math.min(AUDIO_BLOCK, plan.samples - audioOffset);
        const data = settings.silent ? new Float32Array(length * CHANNELS)
          : mixPcmChunk(scenes, timeline.scenes, audioOffset, length, gain);
        if (!settings.silent && settings.paperSound) {
          const effects = makePaperPcm(timeline.scenes, { sampleRate: RATE, offset: audioOffset, length, level: settings.voiceover === false ? 1 : .4 });
          for (let i = 0; i < length; i++) for (let ch = 0; ch < CHANNELS; ch++) data[ch * length + i] += effects[i];
        }
        const sample = new AudioSample({ format: 'f32-planar', numberOfChannels: CHANNELS,
          sampleRate: RATE, timestamp: audioOffset / RATE, data });
        if (frame === 0) progress({ progress: 0, elapsed: 0, duration: plan.duration, phase: 'prepare', message: '正在准备第一段声音。', renderMode: 'offline' });
        try { await audio.add(sample); } finally { sample.close(); }
        audioOffset += length;
      }
      drawFrame(canvas, { scenes: viewScenes, settings }, Math.min(frame / settings.fps, timeline.duration - .001));
      if (frame === 0) progress({ progress: 0, elapsed: 0, duration: plan.duration, phase: 'prepare', message: '正在编码第一幅画面。', renderMode: 'offline' });
      await video.add(frame / settings.fps, 1 / settings.fps);
      if (frame % progressStep === 0 || frame === plan.frames - 1) {
        const elapsed = (frame + 1) / settings.fps;
        const sceneIndex = timeline.scenes.findIndex(scene => elapsed < scene.end);
        progress({ progress: .98 * (frame + 1) / plan.frames, elapsed, duration: plan.duration,
          sceneIndex: sceneIndex < 0 ? timeline.scenes.length - 1 : sceneIndex, phase: 'encode', renderMode: 'offline' });
      }
    }
    // All audio has explicit samples through the rounded-up final video frame, including the complete tail.
    if (audioOffset !== plan.samples) throw new Error('离线音轨长度校验失败。');
    audio.close(); video.close();
    progress({ progress: .99, elapsed: plan.duration, duration: plan.duration, sceneIndex: timeline.scenes.length - 1, phase: 'finalize', renderMode: 'offline' });
    await output.finalize();
    if (!target.buffer?.byteLength) throw new Error('离线编码未生成文件。');
    const mimeType = await output.getMimeType();
    const duration = await inspectEncoded(target.buffer, plan.duration, settings.fps);
    done = true;
    progress({ progress: 1, elapsed: duration, duration, sceneIndex: timeline.scenes.length - 1, phase: 'done', renderMode: 'offline' });
    return { buffer: target.buffer, mimeType, extension: encoding.extension, duration,
      plannedDuration: timeline.duration, durationSource: 'encoded-packets', cues: timeline.cues,
      renderMode: 'offline', frameCount: plan.frames, audioSamples: plan.samples, audioSampleRate: RATE,
      audioChannels: CHANNELS, videoCodec: encoding.video, audioCodec: encoding.audio };
  } finally {
    if (!done && output.state !== 'finalized' && output.state !== 'canceled') { try { await output.cancel(); } catch { /* original error */ } }
    for (const scene of scenes) { try { scene.image?.close(); } catch { /* transferred copy */ } }
  }
}

if (typeof self !== 'undefined' && typeof self.postMessage === 'function' && typeof document === 'undefined') {
  self.onmessage = async event => {
    if (event.data?.type !== 'render') return;
    try {
      const result = await renderOffline(event.data, value => self.postMessage({ type: 'progress', progress: value }));
      self.postMessage({ type: 'done', result }, [result.buffer]);
    } catch (error) {
      self.postMessage({ type: 'error', error: { name: error.name || 'Error', code: error.code, message: error.message || String(error) } });
    } finally {
      // Also release images when preflight or codec selection fails before an Output exists.
      for (const scene of event.data.scenes ?? []) { try { scene.image?.close(); } catch { /* detached/closed */ } }
    }
  };
}
