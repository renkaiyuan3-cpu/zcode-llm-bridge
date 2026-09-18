#!/usr/bin/env bash
# 把 launchd/ 下的 plist 模板渲染后装入 ~/Library/LaunchAgents 并启动。
#
# 用法:
#   ./launchd/install-launchd.sh grok      # Grok Build Proxy (8080)
#   ./launchd/install-launchd.sh gemini    # CLIProxyAPI Antigravity Gemini (8317)
#   ./launchd/install-launchd.sh codex     # CLIProxyAPI Codex (8327)
#   ./launchd/install-launchd.sh restore   # 思考档位自愈任务（等价于 scripts/install-runtime.sh）
#   ./launchd/install-launchd.sh all       # 以上全部
#
# 为什么模板里用 __HOME__ 占位符：launchd plist 不支持环境变量展开，
# 家目录路径必须在安装时渲染，这样同一份模板在任何机器上都能用。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
UID_VAL="$(id -u)"

install_plist() {
    # $1=模板文件名 $2=label
    local src="$SCRIPT_DIR/$1" dst="$LAUNCH_AGENTS/$1"
    [ -f "$src" ] || { echo "❌ 找不到模板 $src"; exit 1; }
    mkdir -p "$LAUNCH_AGENTS"
    sed "s|__HOME__|$HOME|g" "$src" > "$dst"
    launchctl bootout "gui/$UID_VAL/$2" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_VAL" "$dst"
    launchctl kickstart -k "gui/$UID_VAL/$2" 2>/dev/null || true
    echo "✅ 已安装并启动 $2 ($dst)"
}

case "${1:-all}" in
    grok)
        [ -x "$HOME/.grokbuild-proxy/grokbuild-proxy" ] || {
            echo "❌ 未找到 ~/.grokbuild-proxy/grokbuild-proxy，请先安装 grokbuild-proxy（见 docs/grokbuild-proxy-guide.md）"; exit 1; }
        install_plist com.grokbuild.proxy.plist com.grokbuild.proxy
        ;;
    gemini)
        [ -x "$HOME/.cliproxyapi/cli-proxy-api" ] || {
            echo "❌ 未找到 ~/.cliproxyapi/cli-proxy-api，请先安装 CLIProxyAPI（见 docs/cliproxyapi-gemini-guide.md）"; exit 1; }
        install_plist com.cliproxyapi.plist com.cliproxyapi
        ;;
    codex)
        [ -x "$HOME/.cliproxyapi/cli-proxy-api" ] || {
            echo "❌ 未找到 ~/.cliproxyapi/cli-proxy-api，请先安装 CLIProxyAPI（见 docs/codex-guide.md）"; exit 1; }
        install_plist com.cliproxyapi.codex.plist com.cliproxyapi.codex
        ;;
    restore)
        exec "$REPO_DIR/scripts/install-runtime.sh"
        ;;
    all)
        "$0" grok || echo "（跳过 grok）"
        "$0" gemini || echo "（跳过 gemini）"
        "$0" codex || echo "（跳过 codex）"
        "$0" restore
        ;;
    *)
        echo "用法: $0 {grok|gemini|codex|restore|all}"
        exit 1
        ;;
esac
