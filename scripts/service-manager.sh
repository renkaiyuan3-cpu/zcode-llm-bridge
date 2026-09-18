#!/usr/bin/env bash
# ==============================================================================
# 本地大模型代理管理与健康检查脚本
# 覆盖服务：
#   1. Grok Build Proxy (com.grokbuild.proxy @ 127.0.0.1:8080)
#   2. Antigravity Gemini CLIProxyAPI (com.cliproxyapi @ 127.0.0.1:8317)
#   3. Codex OpenAI CLIProxyAPI (com.cliproxyapi.codex @ 127.0.0.1:8327)
# ==============================================================================

UID_VAL=$(id -u)

check_models() {
    # $1=端口 $2=标签 $3=keys 文件
    local port="$1" label="$2" keys="$3"
    echo -n "$label ($port /v1/models): "
    if [ -f "$keys" ]; then
        local key http_code count
        key=$(head -1 "$keys")
        http_code=$(curl -s -o /tmp/.cpa_models.$$ -w "%{http_code}" -m 3 \
            "http://127.0.0.1:$port/v1/models" -H "Authorization: Bearer $key")
        if [ "$http_code" = "200" ]; then
            count=$(python3 -c "
import json
try:
    print(len(json.load(open('/tmp/.cpa_models.$$')).get('data', [])))
except Exception:
    print('?')
" 2>/dev/null)
            echo "✅ HTTP 200 OK (授权正常, $count 个模型)"
        else
            echo "❌ HTTP 状态码: $http_code"
        fi
        rm -f /tmp/.cpa_models.$$
    else
        echo "❌ 未找到 $keys"
    fi
}

status() {
    echo "==================== [服务运行状态] ===================="
    echo "--- 1. Launchd 注册状态 ---"
    launchctl list | grep -E "grokbuild|cliproxyapi" || echo "未找到运行中的代理服务！"
    echo ""
    echo "--- 2. 端口监听检测 ---"
    lsof -nP -iTCP:8080 -sTCP:LISTEN >/dev/null 2>&1 || echo "❌ 8080 (Grok Build Proxy) 未在监听！"
    lsof -nP -iTCP:8317 -sTCP:LISTEN >/dev/null 2>&1 || echo "❌ 8317 (CLIProxyAPI Gemini) 未在监听！"
    lsof -nP -iTCP:8327 -sTCP:LISTEN >/dev/null 2>&1 || echo "❌ 8327 (CLIProxyAPI Codex) 未在监听！"
    echo "（未列出即表示对应端口正常监听）"
    echo ""
    echo "--- 3. HTTP 接口就绪检测 ---"
    echo -n "Grok Build Proxy (8080 /readyz): "
    curl -s -m 2 http://127.0.0.1:8080/readyz || echo "❌ 无法访问"
    echo ""
    check_models 8317 "CLIProxyAPI Gemini" "$HOME/.cliproxyapi/.keys"
    check_models 8327 "CLIProxyAPI Codex " "$HOME/.cliproxyapi/.keys-codex"
    echo "========================================================"
}

restart_grok() {
    echo "正在重启 Grok Build Proxy..."
    launchctl kickstart -k "gui/$UID_VAL/com.grokbuild.proxy"
    echo "已发送重启指令。"
}

restart_gemini() {
    echo "正在重启 Antigravity Gemini CLIProxyAPI..."
    launchctl kickstart -k "gui/$UID_VAL/com.cliproxyapi"
    echo "已发送重启指令。"
}

restart_codex() {
    echo "正在重启 Codex CLIProxyAPI..."
    launchctl kickstart -k "gui/$UID_VAL/com.cliproxyapi.codex"
    echo "已发送重启指令。"
}

restart_all() {
    restart_grok
    restart_gemini
    restart_codex
    sleep 2
    status
}

show_logs() {
    echo "=== Grok Proxy 最近日志 (~/.grokbuild-proxy/proxy.log) ==="
    tail -n 15 "$HOME/.grokbuild-proxy/proxy.log" 2>/dev/null || echo "无日志"
    echo ""
    echo "=== Gemini Proxy 最近日志 (~/.cliproxyapi/server.log) ==="
    tail -n 15 "$HOME/.cliproxyapi/server.log" 2>/dev/null || echo "无日志"
    echo ""
    echo "=== Codex Proxy 最近日志 (~/.cliproxyapi/codex-server.log) ==="
    tail -n 15 "$HOME/.cliproxyapi/codex-server.log" 2>/dev/null || echo "无日志"
}

case "$1" in
    status)
        status
        ;;
    restart)
        restart_all
        ;;
    restart-grok)
        restart_grok
        ;;
    restart-gemini)
        restart_gemini
        ;;
    restart-codex)
        restart_codex
        ;;
    logs)
        show_logs
        ;;
    *)
        echo "用法: $0 {status|restart|restart-grok|restart-gemini|restart-codex|logs}"
        exit 1
        ;;
esac
