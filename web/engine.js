/** Paper Video Studio — browser-only Canvas/Web Audio video engine.
 * AudioBuffers are supplied by TTS/import. System speech playback is never recorded.
 */
const LEAD = 0.35;
const TAIL = 0.65;
const DEFAULTS = { width: 1080, height: 1920, fps: 30, paper: '#eeece7', ink: '#181716', accent: '#ac1210' };
const FONT = '-apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif';
const KINDS = new Set(['text', 'steps', 'compare', 'image']);
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
const ease = n => 1 - (1 - clamp(n, 0, 1)) ** 3;
const normalized = text => String(text ?? '').replace(/\s+/gu, '');

function getSettings(settings = {}) {
  const value = { ...DEFAULTS, ...settings };
  for (const key of ['width', 'height', 'fps']) value[key] = Number(value[key]);
  if (![value.width, value.height].every(n => Number.isInteger(n) && n >= 240 && n <= 3840 && n % 2 === 0)) {
    throw new Error('视频宽高须为 240–3840 范围内的偶数。');
  }
  if (!Number.isInteger(value.fps) || value.fps < 1 || value.fps > 60) throw new Error('帧率须为 1–60 的整数。');
  for (const key of ['paper', 'ink', 'accent']) {
    if (!/^#[a-f\d]{6}$/iu.test(value[key])) throw new Error(`${key} 颜色须使用 #RRGGBB 格式。`);
  }
  return value;
}

function audioDuration(scene) {
  const duration = Number(scene.audio?.duration);
  return Number.isFinite(duration) && duration > 0 ? duration : 0;
}

/** Returns start/end times in seconds. Optional scene.cues are relative to its AudioBuffer. */
export function estimateTimeline(scenes = []) {
  if (!Array.isArray(scenes)) throw new Error('场景列表格式不正确。');
  const cues = [];
  let position = 0;
  const timeline = scenes.map((input, index) => {
    const scene = { ...input };
    if (!KINDS.has(scene.kind)) throw new Error(`第 ${index + 1} 场的画面类型不受支持。`);
    const narration = String(scene.narration ?? '');
    const audio = audioDuration(scene);
    const requested = Number(scene.duration) || 0;
    const estimatedVoice = narration.trim() ? Math.max(1.2, [...narration].length / 4.5) : 0;
    const duration = Math.max(requested, audio ? LEAD + audio + TAIL : Math.max(3, LEAD + estimatedVoice + TAIL));
    if (!Number.isFinite(duration) || duration > 3600) throw new Error(`第 ${index + 1} 场时长超出支持范围。`);
    let captionCues = [];
    if (narration.trim()) {
      if (Array.isArray(scene.cues) && scene.cues.length) {
        if (normalized(scene.cues.map(c => c.text).join('')) !== normalized(narration)) {
          throw new Error(`第 ${index + 1} 场字幕与旁白原文不一致，请重新生成配音。`);
        }
        let previousEnd = 0;
        captionCues = scene.cues.map(cue => {
          const start = Number(cue.start), end = Number(cue.end);
          const limit = audio || duration - LEAD - TAIL;
          if (!(Number.isFinite(start) && Number.isFinite(end) && start >= previousEnd - 0.002 && end > start && end <= limit + 0.002)) {
            throw new Error(`第 ${index + 1} 场字幕时间超出配音范围或相互重叠。`);
          }
          previousEnd = end;
          return { start: LEAD + Math.max(0, start), end: LEAD + Math.min(limit, end), text: String(cue.text) };
        });
      } else {
        // With only a whole-scene buffer, display the full source text. Do not invent word timestamps.
        captionCues = [{ start: LEAD, end: audio ? LEAD + audio : duration - TAIL, text: narration }];
      }
    }
    const result = { ...scene, narration, index, start: position, end: position + duration, duration,
      audioStart: position + LEAD, audioEnd: position + LEAD + audio, audioDuration: audio, captionCues };
    for (const cue of captionCues) cues.push({ ...cue, start: position + cue.start, end: position + cue.end, sceneId: scene.id ?? `s${index + 1}` });
    position += duration;
    return result;
  });
  return { scenes: timeline, duration: position, cues };
}

function font(ctx, size, weight = 500) { ctx.font = `${weight} ${size}px ${FONT}`; }

function wrapped(ctx, text, width, size, weight) {
  font(ctx, size, weight);
  const lines = [];
  for (const paragraph of String(text).replace(/\t/gu, '    ').split('\n')) {
    let line = '';
    for (const char of paragraph) {
      if (line && ctx.measureText(line + char).width > width) {
        const wordBreak = line.lastIndexOf(' ');
        if (wordBreak > line.length * 0.45) {
          lines.push(line.slice(0, wordBreak));
          line = line.slice(wordBreak + 1) + char;
        } else { lines.push(line); line = char; }
      } else line += char;
    }
    lines.push(line);
  }
  return lines;
}

function fit(ctx, text, box, max = 56, min = 26, weight = 500, name = '文字') {
  for (let size = max; size >= min; size -= 2) {
    const lines = wrapped(ctx, text, box.w, size, weight);
    const lineHeight = size * 1.36;
    if (lines.length * lineHeight <= box.h && lines.every(line => ctx.measureText(line).width <= box.w + 0.5)) {
      return { lines, size, lineHeight, weight };
    }
  }
  throw new Error(`${name}过长，无法完整放入画面。请拆成更多分镜，或为长旁白重新生成逐句配音和字幕。`);
}

function textBlock(ctx, text, box, color, options = {}) {
  const { max = 56, min = 26, weight = 500, center = false, name = '文字' } = options;
  const layout = fit(ctx, text, box, max, min, weight, name);
  ctx.fillStyle = color; font(ctx, layout.size, weight);
  ctx.textBaseline = 'top'; ctx.textAlign = center ? 'center' : 'left';
  layout.lines.forEach((line, i) => ctx.fillText(line, center ? box.x + box.w / 2 : box.x, box.y + i * layout.lineHeight));
  return layout;
}

function geometry(settings) {
  const landscape = settings.width > settings.height;
  const w = landscape ? 1920 : 1080, h = landscape ? 1080 : 1920;
  return { w, h, landscape, margin: w * 0.085,
    title: { x: w * .08, y: h * .145, w: w * .84, h: h * (landscape ? .15 : .17) },
    stage: { x: w * .085, y: h * (landscape ? .335 : .36), w: w * .83, h: h * (landscape ? .36 : .355) },
    captions: { x: w * .1, y: h * (landscape ? .78 : .805), w: w * .8, h: h * (landscape ? .12 : .095) } };
}

function stageContents(ctx, scene, g, settings, time) {
  const { stage } = g;
  const inset = g.landscape ? 42 : 48;
  const box = { x: stage.x + inset, y: stage.y + inset, w: stage.w - 2 * inset, h: stage.h - 2 * inset };
  const items = (scene.items ?? []).map(String);
  const slide = 20 * (1 - ease((time - .12) / .25));
  if (scene.kind === 'image') {
    const image = scene.image;
    const iw = image?.naturalWidth || image?.width, ih = image?.naturalHeight || image?.height;
    if (!iw || !ih || image.complete === false) throw new Error(`分镜“${scene.title}”的图片尚未加载或无法读取。`);
    const scale = Math.min(box.w / iw, box.h / ih);
    ctx.drawImage(image, box.x + (box.w - iw * scale) / 2, box.y + (box.h - ih * scale) / 2, iw * scale, ih * scale);
  } else if (scene.kind === 'steps') {
    const values = items.length ? items : [scene.narration];
    const row = box.h / values.length;
    values.forEach((item, i) => {
      const numbered = { x: box.x + 74, y: box.y + row * i + slide, w: box.w - 74, h: row - 15 };
      textBlock(ctx, String(i + 1).padStart(2, '0'), { x: box.x, y: numbered.y, w: 65, h: row - 15 }, settings.accent,
        { max: 36, min: 24, name: '步骤编号' });
      textBlock(ctx, item, numbered, settings.ink, { max: 46, min: 26, name: `第 ${i + 1} 步` });
    });
  } else if (scene.kind === 'compare') {
    const values = items.length ? items : [scene.narration];
    const middle = Math.ceil(values.length / 2);
    const gap = 70;
    const width = (box.w - gap) / 2;
    ctx.strokeStyle = '#dad6cf'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(stage.x + stage.w / 2, box.y); ctx.lineTo(stage.x + stage.w / 2, box.y + box.h); ctx.stroke();
    [values.slice(0, middle), values.slice(middle)].forEach((column, i) => {
      textBlock(ctx, column.join('\n\n'), { x: box.x + i * (width + gap), y: box.y + slide, w: width, h: box.h }, settings.ink,
        { max: 48, min: 26, name: `对比栏 ${i + 1}` });
    });
  } else {
    textBlock(ctx, items.length ? items.join('\n\n') : scene.narration,
      { ...box, y: box.y + slide }, settings.ink, { max: 58, min: 28, name: '正文' });
  }
}

/** Draw one deterministic frame. time is the global timeline time in seconds. */
export function drawFrame(canvas, { scenes = [], settings = {} }, time = 0) {
  const config = getSettings(settings);
  if (canvas.width !== config.width) canvas.width = config.width;
  if (canvas.height !== config.height) canvas.height = config.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('浏览器无法创建画面，请尝试最新版 Chrome、Edge 或 Safari。');
  const timeline = estimateTimeline(scenes);
  const g = geometry(config);
  const scale = Math.min(config.width / g.w, config.height / g.h);
  ctx.save();
  try {
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.fillStyle = config.paper; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.translate((config.width - g.w * scale) / 2, (config.height - g.h * scale) / 2); ctx.scale(scale, scale);
    const now = clamp(Number(time) || 0, 0, Math.max(0, timeline.duration - .001));
    const scene = timeline.scenes.find(s => now < s.end) ?? timeline.scenes.at(-1);
    if (!scene) {
      textBlock(ctx, '从一段文字开始', { x: g.w * .1, y: g.h * .4, w: g.w * .8, h: g.h * .2 }, config.ink,
        { max: 84, min: 32, center: true });
      return { sceneIndex: -1, localTime: 0, duration: 0 };
    }
    const local = now - scene.start;
    const headerY = g.h * .046;
    textBlock(ctx, 'PAPER / VIDEO', { x: g.margin, y: headerY, w: g.w * .6, h: 55 }, config.ink, { max: 30, min: 24 });
    textBlock(ctx, `${String(scene.index + 1).padStart(2, '0')} / ${String(scenes.length).padStart(2, '0')}`,
      { x: g.w - g.margin - 160, y: headerY, w: 160, h: 55 }, config.accent, { max: 30, min: 24 });
    ctx.strokeStyle = config.ink; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(g.margin, g.h * .08); ctx.lineTo(g.w - g.margin, g.h * .08); ctx.stroke();
    textBlock(ctx, { text: '文字讲述', steps: '步骤与流程', compare: '对比说明', image: '图像与讲述' }[scene.kind],
      { x: g.margin, y: g.h * .105, w: g.w * .7, h: 50 }, config.accent, { max: 27, min: 22 });
    const title = fit(ctx, scene.title || '未命名分镜', g.title, g.landscape ? 80 : 88, 34, 650, '标题');
    // The title enters as independently sliding horizontal paper strips; no external template footage.
    for (let yy = 0, i = 0; yy < g.title.h; yy += 36, i++) {
      ctx.save(); ctx.beginPath(); ctx.rect(0, g.title.y + yy, g.w, Math.min(36, g.title.h - yy)); ctx.clip();
      const p = ease((local - i * .012) / .20);
      ctx.translate((1 - p) * (i % 2 ? -100 : 100), 0); ctx.globalAlpha = p;
      textBlock(ctx, scene.title || '未命名分镜', g.title, config.ink, { max: title.size, min: title.size, weight: 650, name: '标题' });
      ctx.restore();
    }
    ctx.fillStyle = '#faf9f5'; ctx.strokeStyle = '#dad6cf'; ctx.lineWidth = 2;
    ctx.fillRect(g.stage.x, g.stage.y, g.stage.w, g.stage.h); ctx.strokeRect(g.stage.x, g.stage.y, g.stage.w, g.stage.h);
    stageContents(ctx, scene, g, config, local);
    const cue = scene.captionCues.find(c => local >= c.start && local < c.end);
    if (cue) textBlock(ctx, cue.text, g.captions, config.ink, { max: 44, min: 28, center: true, name: '字幕' });
    ctx.fillStyle = config.accent; ctx.fillRect(g.margin, g.h * .925, (g.w - 2 * g.margin) * clamp(local / scene.duration, 0, 1), 5);
    ctx.fillStyle = config.ink; ctx.fillRect(g.margin, g.h * .932, g.w - 2 * g.margin, 2);
    textBlock(ctx, '文案 / 声音 / 画面', { x: g.margin, y: g.h * .948, w: g.w * .8, h: 50 }, '#77736e', { max: 24, min: 20 });
    return { sceneIndex: scene.index, localTime: local, duration: timeline.duration };
  } finally { ctx.restore(); }
}

function timestamp(seconds) {
  let ms = Math.max(0, Math.round(Number(seconds) * 1000));
  const hours = Math.floor(ms / 3600000); ms %= 3600000;
  const minutes = Math.floor(ms / 60000); ms %= 60000;
  const secs = Math.floor(ms / 1000); ms %= 1000;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')},${String(ms).padStart(3, '0')}`;
}

export function makeSrt(cues = []) {
  return cues.map((cue, i) => {
    if (!(Number.isFinite(cue.start) && Number.isFinite(cue.end) && cue.start >= 0 && cue.end > cue.start)) throw new Error('字幕时间无效。');
    return `${i + 1}\n${timestamp(cue.start)} --> ${timestamp(cue.end)}\n${String(cue.text)}`;
  }).join('\n\n') + (cues.length ? '\n' : '');
}

function abortError() { return new DOMException('已取消导出。', 'AbortError'); }

async function encodedDuration(blob, signal) {
  // MP4 usually carries duration metadata. Some MediaRecorder WebM files do not;
  // in that case the caller returns its measured recording clock with an explicit source.
  if (typeof globalThis.document?.createElement !== 'function') return null;
  const video = document.createElement('video');
  const url = URL.createObjectURL(blob);
  video.preload = 'metadata'; video.muted = true; video.playsInline = true;
  try {
    return await new Promise((resolve, reject) => {
      let settled = false;
      const finish = value => { if (!settled) { settled = true; clean(); resolve(value); } };
      const cancel = () => { if (!settled) { settled = true; clean(); reject(abortError()); } };
      const changed = () => { if (Number.isFinite(video.duration) && video.duration > 0) finish(video.duration); };
      const loaded = () => {
        changed();
        if (!settled && video.duration === Infinity) {
          try { video.currentTime = 1e10; } catch { finish(null); }
        }
      };
      const clean = () => {
        clearTimeout(timer); signal?.removeEventListener('abort', cancel);
        video.removeEventListener('loadedmetadata', loaded); video.removeEventListener('durationchange', changed);
        video.removeEventListener('timeupdate', changed); video.removeEventListener('error', invalid);
      };
      const invalid = () => {
        if (!settled) { settled = true; clean(); reject(new Error('浏览器无法读取刚导出的视频，请降低分辨率后重试。')); }
      };
      const timer = setTimeout(() => finish(null), 3500);
      video.addEventListener('loadedmetadata', loaded); video.addEventListener('durationchange', changed);
      video.addEventListener('timeupdate', changed); video.addEventListener('error', invalid);
      signal?.addEventListener('abort', cancel, { once: true });
      video.src = url;
      if (signal?.aborted) cancel();
    });
  } finally {
    video.removeAttribute('src'); video.load(); URL.revokeObjectURL(url);
  }
}

function selectRecorder(stream, settings) {
  const Recorder = globalThis.MediaRecorder;
  const candidates = ['video/mp4;codecs=avc1.42E01E,mp4a.40.2', 'video/mp4;codecs=avc1,mp4a.40.2', 'video/mp4',
    'video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm'];
  for (const mimeType of candidates) {
    if (!Recorder.isTypeSupported(mimeType)) continue;
    try {
      return new Recorder(stream, { mimeType, videoBitsPerSecond: settings.width * settings.height * settings.fps * .14,
        audioBitsPerSecond: 192000 });
    } catch { /* The next supported encoder may accept this particular stream. */ }
  }
  throw new Error('此浏览器没有可用的视频编码器。请尝试最新版 Chrome、Edge 或 Safari。');
}

/** Export in real time. onProgress receives {progress,elapsed,duration,sceneIndex}.
 * settings.silent === true is required to intentionally omit missing narration audio.
 */
export async function exportVideo({ canvas, scenes, settings = {}, onProgress = () => {}, signal }) {
  const config = getSettings(settings);
  const timeline = estimateTimeline(scenes);
  if (!timeline.scenes.length) throw new Error('请先添加文案和分镜。');
  if (signal?.aborted) throw abortError();
  if (globalThis.document?.visibilityState === 'hidden') throw new Error('请切回此页面，再开始导出视频。');
  if (typeof canvas?.captureStream !== 'function' || typeof globalThis.MediaRecorder !== 'function') {
    throw new Error('此浏览器不支持画面录制，请使用最新版 Chrome、Edge 或 Safari。');
  }
  const Context = globalThis.AudioContext || globalThis.webkitAudioContext;
  if (!Context) throw new Error('此浏览器不支持可导出的音频，请更换浏览器。');
  for (const scene of timeline.scenes) {
    if (!config.silent && scene.narration.trim() && !scene.audioDuration) {
      throw new Error(`分镜“${scene.title}”还没有可导出的配音。请先生成或导入配音，或明确选择无声导出。`);
    }
    if (scene.audioDuration && typeof scene.audio.getChannelData !== 'function') throw new Error('配音不是有效的 AudioBuffer，请重新生成。');
  }
  if (!config.silent && !timeline.scenes.some(s => s.audioDuration)) throw new Error('没有可导出的音轨，请先添加配音，或明确选择无声导出。');
  // Preflight every stage and subtitle while no recorder is running.
  for (const scene of timeline.scenes) {
    drawFrame(canvas, { scenes, settings: config }, scene.start + .31);
    for (const cue of scene.captionCues) drawFrame(canvas, { scenes, settings: config }, scene.start + (cue.start + cue.end) / 2);
  }
  drawFrame(canvas, { scenes, settings: config }, 0);
  const externalContext = config.audioContext;
  const audioContext = externalContext || new Context();
  let stream, canvasStream, recorder, frameId, finishingTimer;
  const sources = [];
  const ownNodes = [];
  let visibilityHandler, stateHandler, abortHandler;
  try {
    if (audioContext.state === 'closed') throw new Error('音频环境已关闭，请重新点击制作视频。');
    // This resume happens before the first await, preserving the export button's user gesture.
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => { done(); reject(new Error('音频未能启动，请直接点击导出按钮重试。')); }, 10000);
      const onAbort = () => { done(); reject(abortError()); };
      const done = () => { clearTimeout(timer); signal?.removeEventListener('abort', onAbort); };
      signal?.addEventListener('abort', onAbort, { once: true });
      audioContext.resume().then(() => { done(); resolve(); }, error => { done(); reject(error); });
      if (signal?.aborted) onAbort();
    });
    if (audioContext.state !== 'running') throw new Error('音频未能启动。请点击导出按钮重试。');
    if (signal?.aborted) throw abortError();
    const destination = audioContext.createMediaStreamDestination();
    const gain = audioContext.createGain();
    ownNodes.push(gain, destination);
    let peak = 0;
    if (!config.silent) for (const scene of timeline.scenes) {
      if (!scene.audioDuration) continue;
      for (let ch = 0; ch < scene.audio.numberOfChannels; ch++) {
        const values = scene.audio.getChannelData(ch);
        for (let i = 0; i < values.length; i++) peak = Math.max(peak, Math.abs(values[i]));
      }
    }
    gain.gain.value = peak > 0 ? Math.min(1, .92 / peak) : 1;
    gain.connect(destination);
    if (config.monitorAudio) gain.connect(audioContext.destination);
    canvasStream = canvas.captureStream(config.fps);
    const videoTracks = canvasStream.getVideoTracks();
    const audioTracks = destination.stream.getAudioTracks();
    if (!videoTracks.length || !audioTracks.length) throw new Error('浏览器未创建完整的画面和声音轨道。');
    stream = new MediaStream([...videoTracks, ...audioTracks]);
    recorder = selectRecorder(stream, config);
    const chunks = [];
    const timing = { startEventDelay: null, recordingClockDuration: null };
    const blob = await new Promise((resolve, reject) => {
      let settled = false, started = false, startConfirmed = false, startedAt = 0, lastFrame = -1, lastProgress = -1;
      const fail = error => {
        if (settled) return;
        settled = true;
        if (recorder.state !== 'inactive') { try { recorder.stop(); } catch { /* cleanup below */ } }
        reject(error);
      };
      abortHandler = () => fail(abortError());
      signal?.addEventListener('abort', abortHandler, { once: true });
      visibilityHandler = () => {
        if (globalThis.document?.visibilityState === 'hidden') fail(new Error('导出已停止：请保持此页面在前台，再重新导出。'));
      };
      globalThis.document?.addEventListener('visibilitychange', visibilityHandler);
      stateHandler = () => {
        if (started && audioContext.state !== 'running' && !settled) fail(new Error('声音播放被浏览器暂停，导出已停止。请保持页面在前台并重试。'));
      };
      audioContext.addEventListener('statechange', stateHandler);
      recorder.ondataavailable = event => { if (event.data?.size) chunks.push(event.data); };
      recorder.onerror = event => fail(new Error(`视频编码失败：${event.error?.message || '请降低分辨率或更换浏览器。'}`));
      recorder.onstop = () => {
        if (settled) return;
        if (audioContext.currentTime - startedAt < timeline.duration - .08) return fail(new Error('录制提前停止，未生成完整视频。请降低分辨率后重试。'));
        const type = recorder.mimeType || chunks.find(c => c.type)?.type;
        if (!started || !startConfirmed || !chunks.length || !/video\/(mp4|webm)/iu.test(type || '')) return fail(new Error('浏览器没有生成有效的视频文件。'));
        settled = true;
        resolve(new Blob(chunks, { type }));
      };
      const notify = elapsed => {
        const info = drawFrame(canvas, { scenes, settings: config }, elapsed);
        if (elapsed - lastProgress >= .1 || elapsed >= timeline.duration) {
          lastProgress = elapsed;
          try { onProgress({ progress: clamp(elapsed / timeline.duration, 0, 1), elapsed: Math.min(elapsed, timeline.duration),
            duration: timeline.duration, sceneIndex: info.sceneIndex }); } catch (e) { console.warn('Progress callback failed', e); }
        }
      };
      const tick = () => {
        if (settled) return;
        try {
          const elapsed = Math.max(0, audioContext.currentTime - startedAt);
          if (elapsed >= timeline.duration) {
            notify(timeline.duration - .001);
            try { onProgress({ progress: 1, elapsed: timeline.duration, duration: timeline.duration, sceneIndex: timeline.scenes.length - 1 }); } catch { /* UI callback */ }
            videoTracks[0].requestFrame?.();
            // Keep the already-complete tail for one capture interval; no narration is truncated.
            finishingTimer = setTimeout(() => {
              if (!settled && recorder.state !== 'inactive') {
                timing.recordingClockDuration = audioContext.currentTime - startedAt;
                recorder.stop();
              }
            }, Math.ceil(1000 / config.fps));
            return;
          }
          const targetFrame = Math.floor(elapsed * config.fps);
          if (targetFrame !== lastFrame) { lastFrame = targetFrame; notify(elapsed); videoTracks[0].requestFrame?.(); }
          frameId = requestAnimationFrame(tick);
        } catch (error) { fail(error); }
      };
      // start is an asynchronous notification, not the beginning of the captured
      // timestamps. Waiting for it can add a frozen leading frame and offset audio.
      recorder.onstart = () => {
        startConfirmed = true;
        timing.startEventDelay = audioContext.currentTime - startedAt;
      };
      try {
        started = true; startedAt = audioContext.currentTime;
        // Schedule audio before start() so a delayed start event cannot delay speech.
        const silent = audioContext.createBufferSource();
        silent.buffer = audioContext.createBuffer(1, 1, audioContext.sampleRate);
        silent.loop = true; silent.connect(gain); silent.start(startedAt); sources.push(silent);
        if (!config.silent) for (const scene of timeline.scenes) {
          if (!scene.audioDuration) continue;
          const source = audioContext.createBufferSource(); source.buffer = scene.audio; source.connect(gain);
          source.start(startedAt + scene.audioStart); sources.push(source);
        }
        notify(0);
        recorder.start(250);
        frameId = requestAnimationFrame(tick);
      } catch (error) { fail(new Error(`无法开始视频录制：${error.message}`)); }
      if (signal?.aborted) abortHandler();
    });
    if (blob.size < 256) throw new Error('浏览器生成的视频为空，请重试或更换浏览器。');
    const mimeType = blob.type;
    const extension = /^video\/mp4/iu.test(mimeType) ? 'mp4' : /^video\/webm/iu.test(mimeType) ? 'webm' : null;
    if (!extension) throw new Error('浏览器返回了无法识别的视频格式。');
    const metadataDuration = await encodedDuration(blob, signal);
    const duration = metadataDuration ?? timing.recordingClockDuration;
    if (!(Number.isFinite(duration) && duration > 0)) throw new Error('无法确认导出视频的实际时长，请重试。');
    return { blob, mimeType, extension, duration, plannedDuration: timeline.duration,
      durationSource: metadataDuration ? 'encoded-metadata' : 'recording-audio-clock', timing, cues: timeline.cues };
  } finally {
    if (frameId !== undefined) cancelAnimationFrame(frameId);
    if (finishingTimer !== undefined) clearTimeout(finishingTimer);
    signal?.removeEventListener('abort', abortHandler);
    if (visibilityHandler) globalThis.document?.removeEventListener('visibilitychange', visibilityHandler);
    if (stateHandler) audioContext.removeEventListener('statechange', stateHandler);
    if (recorder?.state !== undefined && recorder.state !== 'inactive') { try { recorder.stop(); } catch { /* already stopped */ } }
    for (const source of sources) {
      try { source.stop(); } catch { /* already ended */ }
      try { source.disconnect(); } catch { /* already disconnected */ }
    }
    for (const node of ownNodes) { try { node.disconnect(); } catch { /* destination has no outgoing connection */ } }
    for (const track of stream?.getTracks() ?? []) track.stop();
    for (const track of canvasStream?.getTracks() ?? []) track.stop();
    if (!externalContext && audioContext.state !== 'closed') await audioContext.close();
  }
}
