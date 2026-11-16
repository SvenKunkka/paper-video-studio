"""Build the small macOS file-picker app using the system AppleScript runtime."""
from pathlib import Path
import plistlib
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = r'''
on run
    try
        activate
        set selectedFile to choose file with prompt "选择要制作成视频的 TXT 或 Markdown 文案" of type {"txt", "md", "markdown", "public.plain-text"}
        set sourcePath to POSIX path of selectedFile
        set appPath to POSIX path of (path to me)
        set rootPath to do shell script "/usr/bin/dirname " & quoted form of appPath
        set pythonPath to rootPath & "/.venv/bin/python"
        set entryPath to rootPath & "/video.py"
        display notification "正在根据所选文案制作视频，完成后会自动打开成片。" with title "文案制作视频"
        set makeCommand to "/usr/bin/env PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin " & quoted form of pythonPath & " " & quoted form of entryPath & " gui --source " & quoted form of sourcePath
        do shell script makeCommand
    on error errorMessage number errorNumber
        if errorNumber is -128 then return
        display dialog errorMessage with title "制作未完成" buttons {"好"} default button "好"
    end try
end run
'''


if __name__ == '__main__':
    destination = ROOT / '文案制作视频.app'
    subprocess.run(['osacompile', '-o', str(destination), '-e', SOURCE], check=True)
    info_path = destination / 'Contents/Info.plist'
    info = plistlib.loads(info_path.read_bytes())
    info['CFBundleIdentifier'] = 'local.shred-kit.script-video'
    info['CFBundleDisplayName'] = '文案制作视频'
    info['CFBundleShortVersionString'] = '1.0.0'
    info['CFBundleVersion'] = '1'
    # osacompile adds unrelated usage strings to every applet. This helper only
    # selects an explicitly chosen file and runs the local renderer.
    for key in list(info):
        if key.endswith('UsageDescription'):
            info.pop(key)
    info_path.write_bytes(plistlib.dumps(info))
    subprocess.run(['codesign', '--force', '--sign', '-', str(destination)], check=True)
    print(destination)
