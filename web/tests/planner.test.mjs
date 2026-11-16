import {test} from 'node:test';
import assert from 'node:assert/strict';
import {planScript} from '../planner.js';
const normalized=s=>s.replace(/\s/gu,'');
test('plain text preserves Markdown-looking characters',()=>{const text='---\n第一段原文。\n---\n\n# 第二段原文。';assert.equal(normalized(planScript(text).scenes.map(s=>s.narration).join('')),normalized(text));});
test('markdown headings are screen titles, body remains complete',()=>{const result=planScript('# 总标题\n\n## 场景\n\n1. 第一步。\n2. 第二步。',{markdown:true});assert.equal(result.title,'总标题');assert.equal(result.scenes[0].kind,'steps');assert.equal(normalized(result.scenes.map(s=>s.narration).join('')),'第一步。第二步。');});
test('long text and punctuation preserve order',()=>{const text='内容保持完整。'.repeat(75)+'最后一句？！';assert.equal(normalized(planScript(text).scenes.map(s=>s.narration).join('')),normalized(text));});
test('local image markers require explicit upload',()=>assert.throws(()=>planScript('说明。\n\n![图](私密路径.png)',{markdown:true}),/添加图片/u));
test('empty input is an actionable error',()=>assert.throws(()=>planScript('   '),/文案/u));
