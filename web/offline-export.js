/** Dedicated-worker export: independent of playback, RAF, and foreground visibility. */
import { estimateTimeline } from './engine.js';

function cancelled() { return new DOMException('已取消导出。', 'AbortError'); }
function checkAbort(signal) { if (signal?.aborted) throw cancelled(); }

export function offlineCapability() {
  const missing = ['Worker', 'OffscreenCanvas', 'VideoEncoder', 'AudioEncoder'].filter(name => typeof globalThis[name] !== 'function');
  return { supported: missing.length === 0, reason: missing.length ? `此浏览器缺少离线编码组件：${missing.join('、')}。` : '' };
}

function unavailable(message) {
  const error = new Error(message);
  error.name = 'OfflineExportUnavailableError'; error.code = 'OFFLINE_UNAVAILABLE';
  return error;
}

/** Copy PCM and images rather than transferring/detaching the user's originals. */
export async function copyOfflineScenes(scenes, { signal, silent = false } = {}) {
  checkAbort(signal);
  const copies = [], transfer = [], images = [];
  try {
    for (let index = 0; index < scenes.length; index++) {
      checkAbort(signal);
      const scene = scenes[index];
      const copy = { id: String(scene.id ?? `s${index + 1}`), kind: scene.kind,
        title: String(scene.title ?? ''), narration: String(scene.narration ?? ''),
        items: (scene.items ?? []).map(String), duration: scene.duration,
        cues: scene.cues?.map(cue => ({ start: Number(cue.start), end: Number(cue.end), text: String(cue.text) })),
        image: null, pcm: null, audioInfo: null };
      if (scene.audio) {
        const audio = scene.audio;
        if (!(Number.isFinite(audio.duration) && audio.duration > 0 && Number.isFinite(audio.sampleRate) && audio.sampleRate > 0)
          || !Number.isInteger(audio.numberOfChannels) || audio.numberOfChannels < 1 || typeof audio.getChannelData !== 'function') {
          throw new Error(`第 ${index + 1} 场配音无效，请重新生成或导入。`);
        }
        const length = audio.length ?? audio.getChannelData(0).length;
        copy.audioInfo = { sampleRate: audio.sampleRate, length, duration: length / audio.sampleRate };
        if (!silent) {
          copy.pcm = [];
          for (let ch = 0; ch < audio.numberOfChannels; ch++) {
            checkAbort(signal);
            const pcm = new Float32Array(audio.getChannelData(ch));
            if (pcm.length !== length) throw new Error(`第 ${index + 1} 场配音的声道长度不一致。`);
            copy.pcm.push(pcm); transfer.push(pcm.buffer);
          }
        }
      }
      if (!silent && copy.narration.trim() && !copy.audioInfo) {
        throw new Error(`分镜“${copy.title}”还没有配音。请先生成配音，或明确选择无声导出。`);
      }
      if (scene.kind === 'image' || scene.image) {
        if (!scene.image) throw new Error(`分镜“${copy.title}”缺少图片。`);
        if (typeof globalThis.createImageBitmap !== 'function') throw unavailable('此浏览器无法为离线渲染复制图片。');
        const image = await createImageBitmap(scene.image);
        images.push(image); checkAbort(signal);
        copy.image = image; transfer.push(image);
      }
      copies.push(copy);
    }
    return { scenes: copies, transfer, images };
  } catch (error) {
    for (const image of images) { try { image.close(); } catch { /* already detached */ } }
    throw error;
  }
}

/** Same result shape as real-time export, but encoded using an independent sample clock. */
export async function exportOfflineVideo({ canvas, scenes, settings = {}, onProgress = () => {}, signal }) {
  void canvas; // The preview canvas remains owned by the UI; the worker creates its own canvas.
  checkAbort(signal);
  const capability = offlineCapability();
  if (!capability.supported) throw unavailable(capability.reason);
  const timeline = estimateTimeline(scenes, settings);
  if (!timeline.scenes.length) throw new Error('请先添加文案和分镜。');
  if (settings.silent !== true && settings.voiceover !== false && !timeline.scenes.some(scene => scene.audioDuration)) throw new Error('没有可导出的配音，请生成配音或选择纸张音效。');
  let worker;
  let copied;
  let abort;
  let idleTimer;
  const safeProgress = value => { try { onProgress(value); } catch (error) { console.warn('Progress callback failed', error); } };
  try {
    safeProgress({ progress: 0, elapsed: 0, duration: timeline.duration, sceneIndex: 0, phase: 'prepare', renderMode: 'offline' });
    copied = await copyOfflineScenes(scenes, { signal, silent: settings.silent === true || settings.voiceover === false });
    checkAbort(signal);
    // Explicit fields keep AudioContext and UI callbacks out of structured clone.
    const config = {};
    for (const key of ['width', 'height', 'fps', 'paper', 'ink', 'accent', 'silent', 'visualStyle', 'voiceover', 'paperSound']) {
      if (settings[key] !== undefined) config[key] = settings[key];
    }
    config.silent = settings.silent === true;
    const result = await new Promise((resolve, reject) => {
      let settled = false;
      const fail = error => { if (!settled) { settled = true; reject(error); } };
      worker = new Worker(new URL('./render-worker.js', document.baseURI), { type: 'module', name: 'paper-video-offline-export' });
      const watchProgress = () => {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(() => {
          worker.terminate();
          fail(new Error('编码长时间没有进展，已停止本次任务。请降低画面大小重试，或展开“其他导出方式”使用兼容录制。'));
        }, 45000);
      };
      abort = () => { worker.terminate(); fail(cancelled()); };
      signal?.addEventListener('abort', abort, { once: true });
      worker.onerror = event => { event.preventDefault?.(); fail(new Error(`离线编码失败：${event.message || '请重试或使用兼容模式。'}`)); };
      worker.onmessageerror = () => fail(new Error('离线编码数据无法读取，请重试。'));
      worker.onmessage = event => {
        if (settled) return;
        const message = event.data;
        if (message?.type === 'progress') { watchProgress(); safeProgress(message.progress); }
        else if (message?.type === 'error') {
          const error = new Error(message.error?.message || '离线编码失败。');
          error.name = message.error?.name || 'Error';
          if (message.error?.code) error.code = message.error.code;
          fail(error);
        } else if (message?.type === 'done') { settled = true; resolve(message.result); }
      };
      worker.postMessage({ type: 'render', scenes: copied.scenes, settings: config }, copied.transfer);
      watchProgress();
      if (signal?.aborted) abort();
    });
    checkAbort(signal);
    if (!(result.buffer instanceof ArrayBuffer) || result.buffer.byteLength < 256
      || !['mp4', 'webm'].includes(result.extension) || !(Number.isFinite(result.duration) && result.duration > 0)) {
      throw new Error('离线编码未生成完整视频，未提供下载。');
    }
    const { buffer, ...metadata } = result;
    const blob = new Blob([buffer], { type: result.mimeType });
    return { ...metadata, blob, renderMode: 'offline' };
  } finally {
    clearTimeout(idleTimer);
    signal?.removeEventListener('abort', abort);
    worker?.terminate();
    for (const image of copied?.images ?? []) { try { image.close(); } catch { /* transferred copy */ } }
  }
}
