# Browser TTS third-party notices / 浏览器配音依赖归属

The browser TTS adapter under `web/tts/` uses the following third-party components. Model inference is local to the visitor's browser. No API key is used; text is not sent to a synthesis service.

| Component | Version / source | Declared license | Purpose |
|---|---|---|---|
| `@uzen/kokoro-js` | 1.2.4 · https://github.com/uzen-zone/kokoro-js | Apache-2.0 | Browser Mandarin and mixed Chinese/English phonemization and Kokoro inference wrapper |
| `@huggingface/transformers` | 4.2.0 · https://github.com/huggingface/transformers.js | Apache-2.0 | Model loading, browser cache, ONNX inference and raw audio |
| `onnxruntime-web` | 1.26.0-dev.20260416-b7804b056c · https://github.com/microsoft/onnxruntime | MIT, with its third-party notices | Browser WebGPU/WASM execution |
| `phonemizer` | 1.2.1 · https://github.com/xenova/phonemizer.js | Apache-2.0 as declared by the npm package; preserve embedded upstream notices | English phonemization in mixed text; runtime data is embedded in the bundled JS |
| `pinyin-pro` | Resolved by the application lockfile; package range in Kokoro wrapper is `^3.28.1` · https://github.com/zh-lx/pinyin-pro | MIT | Mandarin phonetic conversion |
| Kokoro-82M-v1.1-zh | https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh | Apache-2.0, per model card | Original Mandarin/English model |
| ONNX model and voice tensors | https://huggingface.co/onnx-community/Kokoro-82M-v1.1-zh-ONNX | Apache-2.0, per model card | Browser-ready weights and voices |

The application build must retain the license notices of bundled dependencies. Full dependency resolution is recorded in the application's npm lockfile. This file records the TTS components; it does not change the repository's existing code license.

## Vendored ONNX Runtime files

The following files are copied unmodified from the exact npm release archive:

`https://registry.npmjs.org/onnxruntime-web/-/onnxruntime-web-1.26.0-dev.20260416-b7804b056c.tgz`

| File | Bytes | SHA-256 |
|---|---:|---|
| `web/tts/vendor/ort-wasm-simd-threaded.asyncify.mjs` | 47,389 | `5959c6733039619c9af710d8e1bae8d6e84402787990637be987c2b1bd6c5fa9` |
| `web/tts/vendor/ort-wasm-simd-threaded.asyncify.wasm` | 23,567,050 | `e0c0c6d3e73d43b8a249972f8358f845b08cc16fec3c80efafdf8bed40366786` |

Transformers.js 4.2.0 uses the package's `ort.webgpu.bundle.min.mjs` browser entry and its native WebGPU EP. This requires the **asyncify** runtime factory exporting `webgpuInit`; the legacy JSEP factory from the same npm version is not compatible with this entry. The vendored factory is instantiated in the tests to verify that its native initialization entry points are present.

The runtime license and bundled third-party notices are retained under `web/tts/vendor/`. These runtime files are served from the same deployed site. No runtime JavaScript is fetched from a third-party CDN.

## Downloaded model resources

Weights are downloaded on demand from the official model repository and cached in the browser. The application does not redistribute model files inside its Git repository.

- FP32 ONNX model (the application default): 339,369,442 bytes.
- The upstream repository also supplies an FP16 model (163,630,554 bytes); this application does not select it automatically because non-finite output was observed on a browser/GPU combination.
- One selected voice tensor: 522,240 bytes.
- Defaults: `zf_001`, 24,000 Hz mono PCM.

The Chinese wrapper's documentation describes known differences from Python Misaki for polyphones, segmentation and text normalization. A successful dependency build does not itself establish pronunciation accuracy on every input.

## Verification boundaries

Unit tests verify lazy/shared loading, preservation of narration text, measured PCM cue timing, cancellation, model retry and rejection of silent output using an injected test runtime. They do not substitute for an actual browser model-inference and audible-export acceptance test.
