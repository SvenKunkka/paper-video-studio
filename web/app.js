// Paper Video Studio, 2026-11-16. GPL-3.0-or-later.
import { planScript, exportPlan } from './planner.js';
import { drawFrame, estimateTimeline, exportVideo, makeSrt } from './engine.js';
import { synthesizeScene, VOICES } from './tts/index.js';
import { readScriptFile } from './files.js';
import { offlineCapability } from './offline-export.js';
import { makePaperPcm } from './paper-audio.js';

const $ = id => document.getElementById(id);
const state = {scenes:[],assets:[],selected:0,title:'我的视频',dirty:true,busy:false,time:0,controller:null,result:null,sourceNodes:[],playing:false,extraURLs:[]};
let context, frame, resultURL, lastTimestamp;
const fmt = seconds => `${Math.floor(seconds/60)}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
const kindLabels = {text:'文字',steps:'步骤',compare:'对比',image:'图片'};
const demo = '# 让想法，重新成形\n\n## 从一张纸开始\n\n文字和图片被排进一张海报。纸张被撕开，飘落，穿过旋转的刀片。\n\n## 再次成形\n\n纸条逐一归位，重新拼成海报。你写下的内容，成为这支短片的一部分。';
for (const voice of VOICES) { const option=new Option(voice.label,voice.id); $('voice').append(option); }
$('voice').options[0].remove();

function settings() {
  const size=Number($('resolution').value), landscape=$('aspect').value==='landscape';
  return {width:landscape?Math.round(size*16/9/2)*2:size,height:landscape?size:Math.round(size*16/9/2)*2,
    fps:30,paper:'#eeece7',ink:'#181716',accent:$('accent').value,visualStyle:$('visual-style').value,
    voiceover:$('sound-mode').value==='voice',paperSound:$('visual-style').value==='paper3d'};
}
function status(message,error=false,progress) {
  $('status').textContent=message; $('status').classList.toggle('error',error);
  if (progress!==undefined) { $('progress').hidden=false; $('progress').value=Math.max(0,Math.min(1,progress)); }
}
function clearResult() {
  stopPreview(); document.querySelector('.playbar').hidden=false;
  state.result=null; $('downloads').hidden=true; $('result-video').pause(); $('result-video').hidden=true; $('preview').hidden=false;
  if (resultURL) { URL.revokeObjectURL(resultURL); resultURL=null; $('result-video').removeAttribute('src'); }
  for(const url of state.extraURLs)URL.revokeObjectURL(url);state.extraURLs=[];
}
function setBusy(value) {
  state.busy=value;
  for (const node of document.querySelectorAll('input,textarea,select,button')) {
    if (node.id!=='cancel') node.disabled=value;
  }
  $('cancel').hidden=!value;
  if (!value) { $('progress').hidden=true; state.controller=null; }
  lockStaleEditor();
  updateSoundControls();
}
function updateSoundControls(){
  const effects=$('sound-mode').querySelector('option[value="effects"]');
  effects.disabled=$('visual-style').value==='cards';
  if(effects.disabled&&$('sound-mode').value==='effects')$('sound-mode').value='voice';
  for(const id of ['voice','speed'])$(id).disabled=state.busy||!settings().voiceover;
}
function lockStaleEditor() {
  for(const node of $('scene-editor').querySelectorAll('input,textarea,select'))node.disabled=state.busy||state.dirty;
  for(const node of $('scenes').querySelectorAll('button'))node.disabled=state.busy||state.dirty;
}
function timeline() { return estimateTimeline(state.scenes,settings()); }
function refresh() {
  const t=timeline();
  document.querySelector('.preview-stage').classList.toggle('landscape',$('aspect').value==='landscape');
  $('timeline-meta').textContent=state.scenes.length?`${state.scenes.length} 个镜头 · ${fmt(t.duration)}`:'等待文案';
  $('seek').max=Math.max(t.duration,.01); $('seek').value=state.time;
  $('time').value=`${fmt(state.time)} / ${fmt(t.duration)}`;
  const ready=state.scenes.length&&state.scenes.every(scene=>scene.audio);
  $('timing-note').textContent=!settings().voiceover?'每张海报演出一段完整动画，默认只配纸张与机器音效。':ready?'时长和字幕已按实际配音对齐。':'启用中文解说后，镜头长度会跟随实际声音调整。';
  try { drawFrame($('preview'),{scenes:state.scenes,settings:settings()},state.time); }
  catch(error) { status(error.message,true); }
}
function renderCards() {
  $('scenes').replaceChildren();
  state.scenes.forEach((scene,index)=>{
    const button=document.createElement('button'); button.className='scene-card'+(index===state.selected?' active':'');
    button.disabled=state.busy||state.dirty;
    button.setAttribute('aria-pressed',String(index===state.selected));
    const meta=document.createElement('span'); meta.textContent=`镜头 ${String(index+1).padStart(2,'0')} / ${kindLabels[scene.kind]}${scene.audio?' / 已配音':''}`;
    const title=document.createElement('strong'); title.textContent=scene.title;
    button.append(meta,title); button.onclick=()=>selectScene(index); $('scenes').append(button);
  });
}
function selectScene(index) {
  if(state.dirty){status('上方文案已修改，请先整理分镜，再编辑镜头。');return;}
  stopPreview(); state.selected=index; const scene=state.scenes[index];
  if(!scene)return;
  $('scene-editor').hidden=false; $('scene-title').value=scene.title; $('scene-narration').value=scene.narration; $('scene-kind').value=scene.kind;
  imageOptions(); state.time=timeline().scenes[index].start+(settings().visualStyle==='paper3d'?0:.33);
  clearResult(); renderCards(); refresh();
  lockStaleEditor();
}
function imageOptions() {
  $('scene-image').replaceChildren(new Option('不使用图片',''));
  state.assets.forEach(asset=>$('scene-image').append(new Option(asset.name,asset.id)));
  $('scene-image').value=state.scenes[state.selected]?.imageId||'';
}
function buildPlan() {
  stopPreview();
  const plan=planScript($('script').value,{markdown:$('script-format').value==='markdown'});
  state.scenes=plan.scenes; state.title=plan.title; state.dirty=false; state.time=0; clearResult(); selectScene(0);
  status(`已整理成 ${state.scenes.length} 个镜头。可以在下方修改分镜，或直接制作。`);
}
function ensurePlan() { if(state.dirty||!state.scenes.length)buildPlan(); }
function reportError(error) {
  if(error?.code==='OFFLINE_UNAVAILABLE'){status('此浏览器暂不支持后台导出。可使用下方“兼容前台录制”，或换用最新版 Chrome、Edge、Safari。',true);return;}
  status(error?.name==='AbortError'?'已取消制作，已完成的配音仍可复用。':error?.message||'制作未完成，请重试。',error?.name!=='AbortError');
}
function filename() { return state.title.replace(/[\\/:*?"<>|]/gu,'-').slice(0,48)||'paper-video'; }
async function prepareExtraDownloads(cues) {
  drawFrame($('preview'),{scenes:state.scenes,settings:settings()},settings().visualStyle==='paper3d'?0:.5);
  const cover=await new Promise(resolve=>$('preview').toBlob(resolve,'image/png'));
  if(!cover)throw new Error('封面未能生成，请降低画面大小后重试。');
  for(const [id,blob,suffix] of [
    ['download-srt',new Blob([makeSrt(cues)],{type:'application/x-subrip;charset=utf-8'}),'.srt'],
    ['download-plan',new Blob([JSON.stringify(exportPlan(state.scenes,settings()),null,2)],{type:'application/json'}),'.json'],
    ['download-cover',cover,'-cover.png'],
  ]){const url=URL.createObjectURL(blob);state.extraURLs.push(url);$(id).href=url;$(id).download=filename()+suffix;}
}
function stopPreview() {
  state.playing=false; cancelAnimationFrame(frame); $('play').textContent='播放';
  for(const source of state.sourceNodes){try{source.stop();source.disconnect();}catch{}}
  state.sourceNodes=[];
}
function ensureContext() {
  const Context=window.AudioContext||window.webkitAudioContext;
  if(!Context)throw new Error('浏览器不支持声音处理。请使用最新版 Chrome、Edge 或 Safari。');
  if(!context||context.state==='closed')context=new Context();
  context.resume(); return context;
}
async function preview() {
  ensurePlan(); if(state.playing){stopPreview();return;}
  clearResult(); const ctx=ensureContext(); await ctx.resume(); const t=timeline();
  if(state.time>=t.duration-.08)state.time=0;
  let effect;
  if(settings().paperSound){
    const pcm=makePaperPcm(t.scenes,{sampleRate:48000,level:settings().voiceover ? .4 : 1});
    effect=ctx.createBuffer(1,pcm.length,48000);effect.copyToChannel(pcm,0);
  }
  const startedAt=ctx.currentTime,offset=state.time;
  if(settings().voiceover)for(const scene of t.scenes){
    if(!scene.audio||scene.audioEnd<=offset)continue;
    const source=ctx.createBufferSource();source.buffer=scene.audio;source.connect(ctx.destination);
    const bufferOffset=Math.max(0,offset-scene.audioStart);source.start(startedAt+Math.max(0,scene.audioStart-offset),bufferOffset);state.sourceNodes.push(source);
  }
  if(effect){
    const source=ctx.createBufferSource();source.buffer=effect;source.connect(ctx.destination);source.start(startedAt,offset);state.sourceNodes.push(source);
  }
  state.playing=true; $('play').textContent='暂停';
  const tick=()=>{if(!state.playing)return;state.time=Math.min(t.duration,offset+ctx.currentTime-startedAt);refresh();if(state.time>=t.duration){stopPreview();return;}frame=requestAnimationFrame(tick);};tick();
}
function ttsProgress(event,index,total) {
  const part=typeof event.progress==='number'?event.progress/100:0;
  status(`镜头 ${index+1}/${total}：${event.message||'正在生成中文配音。'}`,false,Math.min(.65,(index+part)/Math.max(1,total)*.65));
}
async function makeAudio(signal) {
  const voice=$('voice').value,speed=Number($('speed').value);
  for(let index=0;index<state.scenes.length;index++){
    if(signal.aborted)throw new DOMException('已取消','AbortError');
    const scene=state.scenes[index];
    const key=JSON.stringify([scene.narration,voice,speed]);
    if(scene.audio&&scene.audioKey===key)continue;
    const result=await synthesizeScene(scene.narration,{voice,speed,signal,onProgress:event=>ttsProgress(event,index,state.scenes.length)});
    if(signal.aborted)throw new DOMException('已取消','AbortError');
    scene.audio=result.audio;scene.cues=result.cues;scene.audioKey=key;
    renderCards();refresh();
  }
}
async function produce(audioOnly=false,exportMode='offline') {
  if(state.busy)return;
  try{
    stopPreview();ensurePlan();
    if(audioOnly)$('sound-mode').value='voice';
    if(!audioOnly&&exportMode==='offline'&&!offlineCapability().supported){const error=new Error('后台导出不可用');error.code='OFFLINE_UNAVAILABLE';throw error;}
    const ctx=!audioOnly&&exportMode==='realtime'?ensureContext():null;clearResult();
    state.controller=new AbortController();const signal=state.controller.signal;setBusy(true);
    if(settings().voiceover)await makeAudio(signal);
    if(audioOnly){status('中文配音已生成。可以播放试听，或点击“制作视频”导出。');return;}
    status(exportMode==='offline'?'正在准备后台导出。':'兼容录制即将开始，请保持页面在前台。',false,.65);
    const result=await exportVideo({canvas:$('preview'),scenes:state.scenes,settings:{...settings(),exportMode,audioContext:ctx},signal,
      onProgress:info=>{
        state.time=info.elapsed;
        const message=exportMode==='offline'?(info.message||(info.phase==='finalize'?'画面已生成，正在整理视频文件。':`正在生成画面 ${Math.round(info.progress*100)}%，可切换标签页。`)):`正在录制 ${fmt(info.elapsed)} / ${fmt(info.duration)}，请保持页面在前台。`;
        status(message,false,.65+info.progress*.35);document.title=`${Math.round(info.progress*100)}% · 正在生成视频`;
        $('seek').value=info.elapsed;$('time').value=`${fmt(info.elapsed)} / ${fmt(info.duration)}`;
      }});
    const finishedInBackground=document.hidden;
    state.result=result;resultURL=URL.createObjectURL(result.blob);$('download-video').href=resultURL;
    $('download-video').download=`${filename()}.${result.extension}`;$('download-video').textContent=`下载视频 · ${result.extension.toUpperCase()}`;
    await prepareExtraDownloads(result.cues);
    $('result-video').src=resultURL;$('result-video').hidden=false;$('preview').hidden=true;$('downloads').hidden=false;
    document.querySelector('.playbar').hidden=true;
    status(`视频已完成：${fmt(result.duration)}，${result.extension.toUpperCase()}，${settings().voiceover?'含中文解说与字幕':'含纸张与机器音效'}。${finishedInBackground?'本次已在后台完成。':''}`);
  }catch(error){reportError(error);}finally{setBusy(false);renderCards();refresh();document.title=state.result?'✓ 视频已完成 · Paper Video Studio':'Paper Video Studio · 文案制作视频';}
}

$('script').addEventListener('input',()=>{state.dirty=true;$('char-count').textContent=`${$('script').value.length} 字`;clearResult();lockStaleEditor();status('文案已修改，请先整理分镜，再编辑镜头。直接制作也会使用新文案。');});
$('script-format').onchange=()=>{state.dirty=true;clearResult();lockStaleEditor();};
$('load-demo').onclick=()=>{$('script').value=demo;$('script-format').value='markdown';$('char-count').textContent=`${demo.length} 字`;state.dirty=true;try{buildPlan();}catch(error){reportError(error);}};
$('plan').onclick=()=>{try{buildPlan();}catch(error){reportError(error);}};
$('make').onclick=()=>produce(false);$('audio-only').onclick=()=>produce(true);$('cancel').onclick=()=>state.controller?.abort();
$('make-compatible').onclick=()=>produce(false,'realtime');
$('play').onclick=()=>preview().catch(reportError);
$('seek').oninput=()=>{stopPreview();state.time=Number($('seek').value);refresh();};
for(const id of ['aspect','resolution','accent','visual-style','sound-mode'])$(id).onchange=()=>{stopPreview();clearResult();if(id==='visual-style')state.time=0;updateSoundControls();refresh();};
for(const id of ['voice','speed'])$(id).onchange=()=>{stopPreview();for(const scene of state.scenes){scene.audio=null;scene.cues=[];scene.audioKey=null;}$('speed-value').value=`${Number($('speed').value).toFixed(2).replace(/0$/u,'')} 倍`;clearResult();renderCards();refresh();status('声音设置已修改，下次制作会重新生成配音。');};
$('script-file').onchange=async event=>{
  try{const file=event.target.files[0];if(!file)return;const {text,format}=await readScriptFile(file);
    $('script').value=text;$('script-format').value=format;$('char-count').textContent=`${text.length} 字`;state.dirty=true;buildPlan();
  }catch(error){reportError(error);}finally{event.target.value='';}
};
$('image-file').onchange=async event=>{
  try{for(const file of event.target.files){if(file.size>20*1024*1024)throw new Error('单张图片请控制在 20 MB 以内。');const url=URL.createObjectURL(file),image=new Image();image.src=url;try{await image.decode();}catch{URL.revokeObjectURL(url);throw new Error(`无法读取图片“${file.name}”，请使用 PNG、JPG 或 WebP。`);}state.assets.push({id:crypto.randomUUID(),name:file.name,url,image});}renderAssets();imageOptions();status('图片已添加，在下方选择镜头并关联图片。');
  }catch(error){reportError(error);}finally{event.target.value='';}
};
function renderAssets(){
  $('assets').replaceChildren();
  if(!state.assets.length){const hint=document.createElement('p');hint.className='empty-hint';hint.textContent='可选。添加产品图、插图或照片，再把它关联到镜头。';$('assets').append(hint);}
  state.assets.forEach(asset=>{const box=document.createElement('div');box.className='asset';const img=document.createElement('img');img.src=asset.url;img.alt=asset.name;const text=document.createElement('span');text.textContent=asset.name;const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label',`移除图片 ${asset.name}`);remove.onclick=()=>{for(const scene of state.scenes){if(scene.imageId===asset.id){scene.imageId=null;scene.image=null;scene.imageName=null;scene.kind='text';}}URL.revokeObjectURL(asset.url);state.assets=state.assets.filter(v=>v!==asset);renderAssets();selectScene(state.selected);};box.append(img,text,remove);$('assets').append(box);});
}
function editedScene({voiceChanged=false}={}){
  if(state.dirty){status('上方文案已修改，请先整理分镜，再编辑镜头。');return;}
  const scene=state.scenes[state.selected];if(!scene)return;stopPreview();
  scene.title=$('scene-title').value;scene.narration=$('scene-narration').value;
  scene.items=scene.narration.split(/\n|(?<=[。！？!?；;])/u).map(s=>s.trim()).filter(Boolean);
  scene.kind=$('scene-kind').value;
  if(voiceChanged){scene.audio=null;scene.audioKey=null;scene.cues=[];}
  clearResult();renderCards();refresh();status('分镜已单独修改，制作将采用下方分镜中的内容。');
}
$('scene-title').oninput=()=>editedScene();$('scene-narration').oninput=()=>editedScene({voiceChanged:true});
$('scene-kind').onchange=()=>{if($('scene-kind').value==='image'&&!state.scenes[state.selected]?.image){status('请先给这个镜头关联一张图片。',true);$('scene-kind').value=state.scenes[state.selected].kind;return;}editedScene();};
$('scene-image').onchange=()=>{const scene=state.scenes[state.selected],asset=state.assets.find(a=>a.id===$('scene-image').value);scene.image=asset?.image||null;scene.imageId=asset?.id||null;scene.imageName=asset?.name||null;scene.kind=asset?'image':'text';$('scene-kind').value=scene.kind;editedScene();};
$('show-canvas').onclick=()=>{$('result-video').pause();$('result-video').hidden=true;$('preview').hidden=false;document.querySelector('.playbar').hidden=false;state.time=settings().visualStyle==='paper3d'?0:.5;refresh();};
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPreview();});
window.addEventListener('beforeunload',()=>{state.controller?.abort();stopPreview();});
$('load-demo').click();
updateSoundControls();
$('render-capability').textContent=offlineCapability().supported?'可切换标签页继续生成；请保持网页打开。休眠或浏览器冻结可能暂停任务。':'此浏览器暂不支持后台导出，可展开“其他导出方式”使用前台兼容录制。';
