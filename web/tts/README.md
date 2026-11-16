# 浏览器本地中文配音

本目录提供真正生成 PCM 的浏览器中文配音接口，不使用系统 `speechSynthesis` 代替可导出的声音。文案在浏览器中推理，不上传到模型托管方；首次使用会下载模型与所选声音文件。

## 接口

```js
import { loadTTS, synthesizeScene, VOICES } from './tts/index.js';

// 仅在用户点击“生成”后调用。可以省略单独load，synthesizeScene会按需加载。
const controller = new AbortController();
await loadTTS({ onProgress: state => console.log(state.message), signal: controller.signal });
const result = await synthesizeScene('这是完整的文案。下一句也会保留。', {
  voice: 'zf_001', speed: 1,
  onProgress: state => console.log(state),
  signal: controller.signal,
});
// result.audio: 单声道 AudioBuffer
// result.cues: [{ start: 秒, end: 秒, text: 对应完整短句 }]
```

模块导入不会启动模型下载。单例模型缓存于当前页面；重复场景共享模型，推理调用排队执行。模型资源使用 Transformers.js 浏览器缓存；本目录不保存或上传用户文案。

`onProgress` 接收对象：

- `stage`: `runtime` / `model` / `ready` / `speech`
- `message`: 可直接向用户显示的中文说明
- `progress`: 当前资源或阶段的百分比，未知时为 null
- 下载时可能有 `loaded`、`total`、`file`、`expectedBytes`、`device`、`dtype`
- 生成时有 `current`、`total`

默认首次模型下载约339 MB（FP32）；界面应保留阶段说明与下载进度，不把某个小资源的100%误当全模型已准备完成。即使WebGPU适配器支持FP16，也不自动启用该精度，因为部分浏览器/GPU组合的Kokoro FP16输出出现过非有限样本。没有可用WebGPU时会明确报告本地CPU模式，使用WASM和FP32，速度取决于设备。

每个自然短句单独合成，以真实PCM样本数决定字幕时间，句间插入80毫秒静音。长且无标点的内容按词边界分段，未删除或省略非空白正文。模型推理失败、空音频、无效样本或静音结果会报中文错误，不会静默导出无声成片。

取消会立即停止当前调用的等待并阻止后续分段。第三方库暂未暴露中止单次ONNX推理或在途下载的接口，因此正在执行的底层工作可能完成后才释放；它的结果会被丢弃。缓存模型可继续用于用户之后的新请求。

## 统一构建接入

上层应用使用本地构建工具打包ESM导入，精确依赖：

```json
{
  "@uzen/kokoro-js": "1.2.4",
  "@huggingface/transformers": "4.2.0"
}
```

不能把裸模块导入直接发给浏览器；由上层Vite/esbuild统一打包。`@uzen/kokoro-js` 会使用 `phonemizer`、`pinyin-pro`；Transformers.js通过浏览器入口使用 `onnxruntime-web/webgpu`。本次核验其对应ORT为 `1.26.0-dev.20260416-b7804b056c`。

构建时把 `web/tts/vendor/` 原样复制到站点输出的 `tts/vendor/`。运行时按 `document.baseURI` 解析此目录，因此也适用于GitHub Pages项目子路径。`.mjs`和`.wasm`必须在同站点可读取，文件名不得改写。模块显式设置本地 `wasmPaths`、单线程及关闭代理，避免要求GitHub Pages不便设置的跨源隔离响应头，也不从CDN动态载入运行时JS。

此版Transformers.js使用ORT的新原生WebGPU后端，必须搭配 `ort-wasm-simd-threaded.asyncify.mjs/.wasm`。同版本npm包里的旧JSEP文件提供的是另一套接口，不能替换；否则会出现 `webgpuInit is not a function`。更换运行时文件后需重建站点并刷新页面，清除该页面已失败的ONNX初始化链；模型下载缓存仍可复用。

模型和声音从官方Hugging Face仓库读取；模型不打包入GitHub源码。中文声音前端仍有多音字、分词和数字归一化的已知差异；浏览器实际音质、长文速度和设备兼容性需要在发布前验收。

第三方归属与许可证见仓库根 `THIRD_PARTY_TTS.md`。
