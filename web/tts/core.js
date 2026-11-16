/** Pure speech orchestration. Runtime/model loading is supplied by index.js. */

export function abortError() {
  const error = new Error('已取消生成配音。');
  error.name = 'AbortError';
  return error;
}

function checkAbort(signal) {
  if (signal?.aborted) throw abortError();
}

function waitWithAbort(promise, signal) {
  checkAbort(signal);
  if (!signal) return promise;
  return new Promise((resolve, reject) => {
    const onAbort = () => reject(abortError());
    signal.addEventListener('abort', onAbort, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', onAbort));
  });
}

function notify(callback, state) {
  if (!callback) return;
  // UI reporting must not turn an otherwise successful synthesis into a failure.
  try { callback(state); } catch { /* Ignore an observer exception. */ }
}

/** Split for readable subtitle cues without deleting non-whitespace content. */
export function splitNaturalText(text, maxLength = 42) {
  if (typeof text !== 'string' || !text.trim()) {
    throw new Error('请输入需要配音的文案。');
  }
  const sentences = text.match(/.+?(?:[。！？!?；;]+[”’」』）)\]】]*|\.+[”’」』）)\]】]*(?=\s|$)|\n|$)/gs) || [];
  const result = [];
  const words = typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter('zh-CN', { granularity: 'word' })
    : null;
  for (const sentence of sentences) {
    const clauses = sentence.match(/.+?(?:[，,：:、]+|$)/gs) || [];
    let current = '';
    const flush = () => {
      if (current.trim()) result.push(current.trim());
      current = '';
    };
    for (const clause of clauses) {
      if (Array.from(current + clause).length <= maxLength) {
        current += clause;
        continue;
      }
      flush();
      const units = words
        ? Array.from(words.segment(clause), item => item.segment)
        : Array.from(clause);
      for (const unit of units) {
        if (Array.from(current + unit).length > maxLength && current.trim()) flush();
        // Very long unbroken tokens are divided, never omitted.
        if (Array.from(unit).length > maxLength) {
          flush();
          const chars = Array.from(unit);
          while (chars.length > maxLength) result.push(chars.splice(0, maxLength).join(''));
          current = chars.join('');
        } else {
          current += unit;
        }
      }
    }
    flush();
  }
  const compact = value => value.replace(/\s/gu, '');
  if (compact(result.join('')) !== compact(text)) {
    throw new Error('配音分段没有完整保留文案，请检查输入内容。');
  }
  return result;
}

export function createSpeechService({ loadRuntime, createAudioBuffer = options => new AudioBuffer(options) }) {
  let model = null;
  let loading = null;
  let lastProgress = null;
  let generationQueue = Promise.resolve();
  const listeners = new Set();
  const report = state => {
    lastProgress = state;
    for (const listener of listeners) notify(listener, state);
  };

  async function loadTTS({ onProgress, signal } = {}) {
    checkAbort(signal);
    if (model) {
      notify(onProgress, { stage: 'ready', progress: 100, message: '中文配音模型已就绪。' });
      return model;
    }
    if (onProgress) {
      listeners.add(onProgress);
      if (lastProgress) notify(onProgress, lastProgress);
    }
    if (!loading) {
      loading = Promise.resolve().then(() => loadRuntime(report)).then(result => {
        model = result;
        report({ stage: 'ready', progress: 100, message: '中文配音模型已就绪。' });
        return model;
      }).catch(error => {
        loading = null;
        lastProgress = null;
        throw error;
      });
    }
    try {
      return await waitWithAbort(loading, signal);
    } finally {
      if (onProgress) listeners.delete(onProgress);
    }
  }

  async function runScene(text, { voice = 'zf_001', speed = 1, onProgress, signal } = {}) {
    checkAbort(signal);
    if (typeof voice !== 'string' || !voice.trim()) throw new Error('请选择配音声音。');
    if (typeof speed !== 'number' || !Number.isFinite(speed) || speed < 0.5 || speed > 2) {
      throw new Error('配音速度需在 0.5–2 倍之间。');
    }
    const sentences = splitNaturalText(text);
    const engine = await loadTTS({ onProgress, signal });
    checkAbort(signal);
    const chunks = [];
    const cues = [];
    let sampleRate = 24000;
    let frames = 0;
    for (let index = 0; index < sentences.length; index += 1) {
      checkAbort(signal);
      notify(onProgress, {
        stage: 'speech', progress: index / sentences.length * 100,
        current: index + 1, total: sentences.length,
        message: `正在生成中文配音 ${index + 1}/${sentences.length}。`,
      });
      let generated;
      try {
        generated = await engine.generate(sentences[index], { voice, speed });
      } catch (error) {
        checkAbort(signal);
        throw new Error(`第 ${index + 1} 段中文配音失败，请重试或缩短该段文案。${error?.message ? `（${error.message}）` : ''}`, { cause: error });
      }
      checkAbort(signal);
      const rawData = generated.data;
      const pcm = new Float32Array(rawData);
      const rate = generated.sampling_rate;
      if (!Number.isInteger(rate) || rate <= 0 || (index > 0 && rate !== sampleRate)) {
        throw new Error('配音采样率无效或发生变化，未导出不完整音频。');
      }
      sampleRate = rate;
      let peak = 0;
      let nonFiniteSamples = 0;
      for (const sample of pcm) {
        if (!Number.isFinite(sample)) nonFiniteSamples += 1;
        else peak = Math.max(peak, Math.abs(sample));
      }
      if (nonFiniteSamples) {
        // Only numerical diagnostics are logged. Never log the user's script.
        console.warn('[TTS PCM validation]', {
          samples: pcm.length, nonFiniteSamples, sampleRate: rate,
          sourceType: rawData?.constructor?.name ?? typeof rawData,
          finitePeak: peak,
        });
        throw new Error('中文配音返回了无效音频样本，未修改或替换为静音。请重新加载页面后重试稳定模式。');
      }
      if (pcm.length < sampleRate * 0.05 || peak < 1e-6) {
        throw new Error(`第 ${index + 1} 段配音没有生成有效声音，未改用无声视频。`);
      }
      cues.push({ start: frames / sampleRate, end: (frames + pcm.length) / sampleRate, text: sentences[index] });
      chunks.push(pcm);
      frames += pcm.length;
      // A short, measured gap makes sentence boundaries clear without guessing timings.
      if (index < sentences.length - 1) {
        const gap = new Float32Array(Math.round(sampleRate * 0.08));
        chunks.push(gap);
        frames += gap.length;
      }
    }
    checkAbort(signal);
    const audio = createAudioBuffer({ numberOfChannels: 1, length: frames, sampleRate });
    let offset = 0;
    for (const chunk of chunks) {
      audio.copyToChannel(chunk, 0, offset);
      offset += chunk.length;
    }
    notify(onProgress, { stage: 'speech', progress: 100, current: sentences.length, total: sentences.length, message: '中文配音生成完成。' });
    return { audio, cues };
  }

  async function synthesizeScene(text, options = {}) {
    // One ONNX session is shared; keep inference calls sequential even if the UI
    // requests several scenes at once. A queued cancelled scene never generates.
    const task = generationQueue.then(() => runScene(text, options));
    generationQueue = task.catch(() => {});
    return waitWithAbort(task, options.signal);
  }

  return { loadTTS, synthesizeScene };
}
