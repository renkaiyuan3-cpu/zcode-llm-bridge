# Grok Build 接入 ZCode 深度指南

## 1. 组件概述

**Grok Build Proxy** 是一个专门针对 xAI Grok Build 订阅服务定制的高性能本地反向代理。
它将 Grok 官方 CLI 的后端接口封装为标准兼容的 **Anthropic Messages 协议**（`/v1/messages`），使支持 Claude 协议的开发工具（如 ZCode、Cursor、Aider 等）能够直接调用 Grok 4.5 与 Grok 4.6 模型。

- **监听地址**：`127.0.0.1:8080`
- **上游地址**：`https://cli-chat-proxy.grok.com/v1`
- **服务托管**：macOS `launchd`（`com.grokbuild.proxy`）
- **程序目录**：`~/.grokbuild-proxy/`
- **Web Admin**：`http://127.0.0.1:8080/admin`

---

## 2. 授权认证与会话隔离机制

### 2.1 为什么必须独立授权？
许多开发者试图直接复用官方 Grok CLI 的授权文件（`~/.grok/auth.json` 或 `~/.grok/cli`）。
**踩坑警告**：
- xAI 后端的 OAuth 采用 Refresh Token 动态轮换机制（Token Rotation）。
- 如果多个客户端共用同一组 Refresh Token，一旦一方发起刷新，另一方的 Token 即刻失效，导致 Grok CLI 与代理服务频繁“打架”踢下线。
- **解决方案**：本代理使用独立设备码授权流程（Device Flow），生成一套全新的独立 Refresh Token，保存在 `~/.grokbuild-proxy/data/meta.json` 中，两套 OAuth 会话完全隔离。

### 2.2 授权配置流程
1. 执行设备登录流程：
   ```bash
   cd ~/.grokbuild-proxy
   # 启动设备授权码交互
   ./grokbuild-proxy -device-login
   ```
2. 终端输出授权链接与验证码：
   - 打开浏览器访问 xAI 设备授权页面，输入确认码完成绑定。
3. 授权成功后，代理自动在 `data/meta.json` 中生成：
   - `api_key`：用于 ZCode 等本地客户端调用的 Bearer Token。
   - `admin_key`：访问 Web Admin 管理界面的密码。
   - `refresh_token`：后台定时自动刷新的凭据。

---

## 3. ZCode 配置注册

使用自动化脚本 `scripts/apply-grok-provider.py` 写入配置：
```bash
python3 scripts/apply-grok-provider.py
```

### 3.1 注入的 Provider 关键字段
```json
{
  "name": "Grok Build (订阅)",
  "kind": "anthropic",
  "apiFormat": "anthropic-messages",
  "source": "custom",
  "options": {
    "apiKey": "<从 meta.json 读取的 api_key>",
    "baseURL": "http://127.0.0.1:8080",
    "apiKeyRequired": true
  },
  "models": {
    "grok-4.6": {
      "name": "Grok 4.6",
      "limit": { "context": 500000, "output": 128000 },
      "modalities": { "input": ["text"], "output": ["text"] },
      "reasoningSpec": { ... }
    },
    "grok-4.5": {
      "name": "Grok 4.5",
      "limit": { "context": 500000, "output": 128000 },
      "modalities": { "input": ["text"], "output": ["text"] },
      "reasoningSpec": { ... }
    }
  }
}
```

---

## 4. 常用维护与故障排除

### 4.1 健康状态检查
```bash
# 检查就绪状态
curl -s http://127.0.0.1:8080/readyz
# 预期返回: {"status":"ready"}

# 查看运行日志
tail -f ~/.grokbuild-proxy/proxy.log
```

### 4.2 重启或重载服务
```bash
launchctl kickstart -k gui/$(id -u)/com.grokbuild.proxy
```

### 4.3 凭据失效处理
如果 `proxy.log` 中频繁出现 `401 Unauthorized` 或 `token_refresh_failed`：
1. 停止代理：`launchctl unload ~/Library/LaunchAgents/com.grokbuild.proxy.plist`
2. 重新执行设备授权：`cd ~/.grokbuild-proxy && ./grokbuild-proxy -device-login`
3. 重新加载服务：`launchctl load ~/Library/LaunchAgents/com.grokbuild.proxy.plist`
4. 重新同步 Key 到 ZCode：`python3 scripts/apply-grok-provider.py`，然后重启 ZCode。
