#!/bin/zsh
TASK_ROOT="${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if [[ ! -x "$TASK_ROOT/.venv/bin/python" ]]; then
    /usr/bin/osascript -e 'display dialog "项目运行环境缺失，请先准备 Python 依赖。" with title "文案制作视频" buttons {"好"}'
    exit 1
fi
exec "$TASK_ROOT/.venv/bin/python" "$TASK_ROOT/video.py" gui
