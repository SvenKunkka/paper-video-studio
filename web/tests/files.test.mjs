import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readScriptFile} from '../files.js';
import {planScript} from '../planner.js';
test('actual UTF-8 File imports through planning with TXT symbols preserved',async()=>{const text='---\n第一段正文\n---\n\n# 第二段正文。';const imported=await readScriptFile(new File([text],'文案 含空格.txt'));const plan=planScript(imported.text,{markdown:imported.format==='markdown'});assert.equal(plan.scenes.map(s=>s.narration).join('').replace(/\s/gu,''),text.replace(/\s/gu,''));});
test('UTF-8 BOM Markdown imports as Markdown',async()=>{const result=await readScriptFile(new File(['\ufeff# 标题\n\n正文。'],'文案.MD'));assert.equal(result.format,'markdown');assert.equal(planScript(result.text,{markdown:true}).title,'标题');});
test('GB18030 text decodes without replacement characters',async()=>{const result=await readScriptFile(new File([Uint8Array.from([0xd6,0xd0,0xce,0xc4])],'中文.txt'));assert.equal(result.text,'中文');});
test('binary, empty and oversized inputs return actionable errors',async()=>{await assert.rejects(()=>readScriptFile(new File(['word'],'文档.docx')),/TXT/u);await assert.rejects(()=>readScriptFile(new File(['A\0B'],'文档.txt')),/空字节/u);await assert.rejects(()=>readScriptFile(new File([' '],'空.txt')),/为空/u);await assert.rejects(()=>readScriptFile(new File(['a'.repeat(512*1024+1)],'太大.txt')),/512/u);});
