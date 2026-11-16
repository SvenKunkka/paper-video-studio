import { createSpeechService } from './core.js';

export const MODEL_ID = 'onnx-community/Kokoro-82M-v1.1-zh-ONNX';
export const DEFAULT_VOICE = 'zf_001';
export const VOICES = [
  { id: 'zf_001', label: '中文女声 01' },
  { id: 'zf_002', label: '中文女声 02' },
  { id: 'zm_010', label: '中文男声 10' },
];

async function chooseBackend() {
  if (typeof navigator !== 'undefined' && navigator.gpu) {
    try {
      const adapter = await navigator.gpu.requestAdapter();
      // Kokoro's FP16 graph can produce non-finite waveform samples on some
      // browser/GPU combinations. Prefer the model's documented FP32 default;
      // GPU availability alone does not establish numerical FP16 compatibility.
      if (adapter) return { device: 'webgpu', dtype: 'fp32' };
    } catch { /* Continue with local WASM if a GPU is unavailable. */ }
  }
  return { device: 'wasm', dtype: 'fp32' };
}

async function loadRuntime(report) {
  report({ stage: 'runtime', progress: 0, message: '正在准备本地中文配音引擎；文案不会上传。' });
  try {
    // These imports are bundled locally by the app build. They are intentionally
    // lazy: visiting the page never starts a model download.
    const [{ KokoroTTS }, { env }] = await Promise.all([
      import('@uzen/kokoro-js'), import('@huggingface/transformers'),
    ]);
    const { device, dtype } = await chooseBackend();
    const assetBase = new URL('./tts/vendor/', document.baseURI);
    env.allowLocalModels = false;
    env.allowRemoteModels = true;
    env.useBrowserCache = true;
    env.backends.onnx.wasm.numThreads = 1;
    env.backends.onnx.wasm.proxy = false;
    // Transformers 4.2 imports ort.webgpu.bundle.min.mjs, whose native WebGPU
    // backend requires the asyncify factory (webgpuInit). The older JSEP
    // factory from the same npm package only exports jsepInit and is incompatible.
    env.backends.onnx.wasm.wasmPaths = {
      mjs: new URL('ort-wasm-simd-threaded.asyncify.mjs', assetBase).href,
      wasm: new URL('ort-wasm-simd-threaded.asyncify.wasm', assetBase).href,
    };
    const expectedBytes = 339369442;
    report({
      stage: 'model', progress: 0, device, dtype, expectedBytes,
      message: `首次使用需下载约 ${Math.ceil(expectedBytes / 1e6)} MB 中文模型并缓存。${device === 'wasm' ? '当前使用浏览器本地 CPU 模式，生成可能较慢。' : '当前使用浏览器 GPU 的 FP32 稳定模式。'}`,
    });
    return await KokoroTTS.from_pretrained(MODEL_ID, {
      device, dtype,
      voicePath: `https://huggingface.co/${MODEL_ID}/resolve/main/voices`,
      progress_callback: event => {
        if (event.status === 'progress') {
          report({
            stage: 'model', progress: Number.isFinite(event.progress) ? event.progress : null,
            loaded: event.loaded, total: event.total, file: event.file, device, dtype, expectedBytes,
            message: `正在下载中文模型${event.file ? `：${event.file}` : ''}。`,
          });
        } else if (event.status === 'done') {
          report({ stage: 'model', progress: 100, file: event.file, device, dtype, expectedBytes, message: '资源已下载，正在初始化中文模型。' });
        }
      },
    });
  } catch (error) {
    const detail = error?.message ? `（${error.message}）` : '';
    throw new Error(`中文配音模型加载失败。请检查网络是否可以访问 Hugging Face、浏览器存储空间及 WebGPU 支持，然后重试。${detail}`, { cause: error });
  }
}

const service = createSpeechService({ loadRuntime });

export const loadTTS = service.loadTTS;
export const synthesizeScene = service.synthesizeScene;
