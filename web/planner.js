// Paper Video Studio, 2026-11-16. GPL-3.0-or-later.
const compact = value => value.replace(/\s/gu, '');
const short = (value, n = 28) => value.length > n ? value.slice(0, n - 1) + '…' : value;

export function planScript(source, {markdown = false} = {}) {
  if (!source.trim()) throw new Error('先写入或导入一份文案。');
  if (source.length > 12000) throw new Error('文案超过 12,000 字，请拆成几集分别制作。');
  let text = source.replace(/^\uFEFF/u, '').replace(/\r\n?/gu, '\n');
  if (markdown && /^---\s*\n/u.test(text)) {
    const meta = text.match(/^---\s*\n[\s\S]*?\n(?:---|\.\.\.)\s*(?:\n|$)/u);
    if (!meta) throw new Error('开头的 Markdown 元数据未闭合，请补上 ---。');
    text = text.slice(meta[0].length);
  }
  let heading = '', title = '', block = [], scenes = [], bodies = [];
  const flush = () => {
    const original = block.join('\n').trim(); block = [];
    if (!original) return;
    let narration = original;
    if (markdown) {
      if (/!\[[^\]]*\]\(/u.test(original)) throw new Error('网页不能读取文案中的本机图片路径。请移除图片标记，再用“添加图片”选择图片并关联镜头。');
      narration = original.split('\n').filter(line => !/^\s*\|?[\s:|-]{4,}\|?\s*$/u.test(line))
        .map(line => line.replace(/^\s*>\s?/u, '').replace(/^\s*(?:[-*+]\s+|\d+[.)、]\s+)/u, '')
          .replace(/^\s*\|/u, '').replace(/\|\s*$/u, '').replace(/\|/gu, '，'))
        .join('\n').replace(/\[([^\]]+)\]\([^)]*\)/gu, '$1').replace(/\*\*([^*]+)\*\*|__([^_]+)__/gu, (_,a,b) => a || b)
        .replace(/`([^`]+)`/gu, '$1').trim();
    }
    if (!narration) return;
    bodies.push(narration);
    const pieces = []; let current = '';
    for (const character of narration) {
      current += character;
      if ((current.length >= 60 && /[。！？!?；;\n]/u.test(character)) || current.length >= 125) {pieces.push(current.trim()); current = '';}
    }
    if (current.trim()) pieces.push(current.trim());
    for (const part of pieces) {
      const items = part.split(/\n|(?<=[。！？!?；;])/u).map(v => v.trim()).filter(Boolean);
      const kind = markdown && /\|.*\|/u.test(original) ? 'compare'
        : markdown && /^\s*(?:\d+[.)、]|[-*+])\s+/mu.test(original) ? 'steps' : 'text';
      scenes.push({id:`s${String(scenes.length + 1).padStart(3,'0')}`, title: heading || short(part.split(/[。！？!?\n]/u)[0]),
        narration:part, items, kind, image:null, audio:null, cues:[]});
    }
  };
  for (const line of text.split('\n')) {
    const match = markdown && line.match(/^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/u);
    if (match) {flush(); heading = match[1]; title ||= heading;}
    else if (!line.trim()) flush();
    else block.push(line);
  }
  flush();
  if (!scenes.length) throw new Error('没有可朗读的正文。请在标题下补上内容。');
  if (compact(scenes.map(scene => scene.narration).join('')) !== compact(bodies.join(''))) throw new Error('分镜完整性检查失败，请检查文案格式。');
  return {title:title || short(scenes[0].title), scenes};
}

export function exportPlan(scenes, settings) {
  return {version:1,settings:Object.fromEntries(Object.entries(settings).filter(([key]) => key !== 'audioContext')),
    scenes:scenes.map(({id,title,narration,kind,items,imageName})=>({id,title,narration,kind,items,image:imageName || null}))};
}
