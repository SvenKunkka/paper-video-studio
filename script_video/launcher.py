"""macOS native file selection. All user paths are data, never shell source."""
from __future__ import annotations

from pathlib import Path
import subprocess


PICK_SCRIPT = '''
on run argv
    try
        set selectedFile to choose file with prompt "选择要制作成视频的 TXT 或 Markdown 文案" of type {"txt", "md", "markdown", "public.plain-text"}
        return POSIX path of selectedFile
    on error number -128
        return ""
    end try
end run
'''

MESSAGE_SCRIPT = '''
on run argv
    display dialog (item 1 of argv) with title "文案制作视频" buttons {"好"} default button "好"
end run
'''


def choose_source() -> Path | None:
    result = subprocess.run(['osascript', '-e', PICK_SCRIPT], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('文件选择器未能打开：' + result.stderr.strip())
    selected = result.stdout.strip('\r\n')
    return Path(selected) if selected else None


def message(value: str) -> None:
    subprocess.run(['osascript', '-e', MESSAGE_SCRIPT, value], capture_output=True, text=True, check=False)


def launch(source: Path | None = None) -> int:
    from video import make_video
    try:
        selected = source or choose_source()
        if selected is None:
            print('已取消选择，未开始制作。')
            return 0
        print(f'已选择：{selected}\n正在制作，请保留这个窗口。', flush=True)
        result = make_video(selected)
        video = result.get('video')
        if not video or not Path(video).is_file():
            raise ValueError('没有生成可打开的视频，请查看制作目录中的错误记录。')
        subprocess.run(['open', video], check=True)
        subprocess.run(['open', '-R', video], check=True)
        print(f'已打开成片：{video}', flush=True)
        return 0
    except Exception as exc:
        print(f'制作未完成：{exc}', flush=True)
        message(f'制作未完成。\n\n{exc}\n\n可在制作窗口中查看详细信息。')
        return 1
