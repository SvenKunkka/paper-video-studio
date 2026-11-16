/** Import text without a server. TXT remains literal; Markdown parsing is separate. */
export async function readScriptFile(file) {
  if (!file || !/\.(txt|md|markdown)$/iu.test(file.name || '')) {
    throw new Error('请选择 TXT 或 Markdown 文案文件。');
  }
  if (file.size > 512 * 1024) throw new Error('文案文件超过 512 KB，请拆成几份后导入。');
  const bytes = await file.arrayBuffer();
  let text;
  try { text = new TextDecoder('utf-8', {fatal:true}).decode(bytes); }
  catch {
    try { text = new TextDecoder('gb18030', {fatal:true}).decode(bytes); }
    catch { throw new Error('无法读取文件编码，请将文案另存为 UTF-8 的 TXT 或 Markdown。'); }
  }
  if (text.includes('\0')) throw new Error('文件含有空字节，请选择纯文本 TXT 或 Markdown。');
  if (!text.trim()) throw new Error('文案文件为空，请先写入正文。');
  return {text,format:/\.(md|markdown)$/iu.test(file.name)?'markdown':'plain'};
}
