#!/usr/bin/env bash
# 把自愈脚本装到 ~/.zcode-proxy 并重装 launchd 任务。
#
# 为什么不直接从本仓库跑：本仓库在 ~/Desktop 下，macOS TCC 会禁止 launchd
# 后台进程读取桌面目录，脚本会以 `Operation not permitted` 静默失败，
# 思考补丁就永远补不回去。运行时副本放在家目录下可绕开该限制。
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$HOME/.zcode-proxy"
PLIST_LABEL="com.zcode.restore-reasoning"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
PYTHON="/usr/bin/python3"

mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

for f in "$REPO_DIR"/scripts/*.py; do
    cp -f "$f" "$RUNTIME_DIR/$(basename "$f")"
done
echo "✅ 已同步脚本到 $RUNTIME_DIR"

cat > "$PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$RUNTIME_DIR/restore-reasoning.py</string>
        <string>--quiet</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$RUNTIME_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>StartInterval</key>
    <integer>60</integer>
    <key>StandardOutPath</key>
    <string>$HOME/.zcode/v2/logs/restore-reasoning.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.zcode/v2/logs/restore-reasoning.err.log</string>
</dict>
</plist>
PLIST
echo "✅ 已写入 $PLIST_DST"

launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
launchctl kickstart -k "gui/$(id -u)/$PLIST_LABEL"
echo "✅ 已重新加载 launchd 任务 $PLIST_LABEL"

sleep 2
if launchctl list "$PLIST_LABEL" >/dev/null 2>&1; then
    status="$(launchctl list "$PLIST_LABEL" | awk -F'= ' '/LastExitStatus/{print $2}' | tr -dc '0-9')"
    echo "   最近退出码: ${status:-0}"
fi
