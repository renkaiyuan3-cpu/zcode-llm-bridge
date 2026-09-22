# 网络环境要求与受限网络配置指南

本项目接入的五个通道里，三个走订阅 OAuth（Grok / Gemini / Codex），它们的上游域名在部分地区需要代理才能访问。
本文说明：每个通道需要连通哪些域名、如何一键自测、以及为什么「终端里设了 HTTP_PROXY 却不生效」。

---

## 1. 各通道上游域名与连通性自测

| 通道 | 上游域名 | 是否需要科学上网* | 测试命令（返回 HTTP 状态码即算 TCP/TLS 通） |
| :--- | :--- | :--- | :--- |
| **Grok Build** | `cli-chat-proxy.grok.com` | 视地区而定 | `curl -s -o /dev/null -w '%{http_code}\n' -m 5 https://cli-chat-proxy.grok.com` |
| **Gemini (Antigravity)** | `cloudcode-pa.googleapis.com` | **大陆需要** | `curl -s -o /dev/null -w '%{http_code}\n' -m 5 https://cloudcode-pa.googleapis.com` |
| **Codex (ChatGPT)** | `chatgpt.com` | **大陆需要** | `curl -s -o /dev/null -w '%{http_code}\n' -m 5 https://chatgpt.com` |
| Command Code | `api.commandcode.ai` | 不需要 | `curl -s -o /dev/null -w '%{http_code}\n' -m 5 https://api.commandcode.ai` |
| OpenCode Go | `opencode.ai` | 不需要 | 同上形式 |

\* 判断标准是**域名能否直连**，与你的物理位置无关：只要上面命令能返回状态码（403/404 都算通——那是服务器在应答，说明链路没问题），就不需要任何额外配置。

**典型症状对照**：

- `curl: (7) Couldn't connect` / `Connection refused` → 网络层不通，走本文第 3 节配置代理。
- `curl: (28) Operation timed out` → 同上，多见于直连被墙。
- 本地代理端口有响应、ZCode 里请求却超时 → launchd 服务没走代理，见第 2 节（最常见的坑）。

---

## 2. 最重要的坑：launchd 服务不继承你的终端环境

三个代理服务（grokbuild-proxy、CLIProxyAPI×2）都是 **launchd 常驻**的。launchd 启动的进程：

1. **不读 `~/.zshrc` / `~/.bashrc`** —— 你在终端里 `export HTTP_PROXY=...` 对它们毫无作用；
2. **不读 macOS「系统设置 → 网络 → 代理」** —— 代理 App 的「系统代理」模式只对主动读取系统代理设置的应用生效（浏览器、ZCode 图形端本身会读），Go 程序默认只认环境变量。

所以「我明明开了 Clash/Surge 系统代理，ZCode 里的 Gemini 还是超时」的根因几乎都是这个：
**代理只覆盖了 ZCode → 本地代理这一段，本地代理 → Google 这一段仍然是裸连。**

解决办法是**把代理写进每个服务自己的配置文件**（下一节），而不是依赖环境变量或系统代理。

> 例外：如果你的代理 App 开了「TUN / 增强模式」（虚拟网卡接管全局路由），所有流量包括 launchd 服务都会被接管，此时无需任何配置。用 `route -n get default` 看 `interface` 是不是 `utun*` 即可确认。

---

## 3. 受限网络配置方法

### 3.1 Gemini（CLIProxyAPI，端口 8317）

编辑 `~/.cliproxyapi/config.yaml`，取消注释 / 添加顶层 `proxy-url`：

```yaml
# 支持 socks5 / http / https，也可单独给某个上游写 "direct"/"none" 绕过
proxy-url: "socks5://127.0.0.1:7890"     # 换成你的代理实际地址端口
```

改完重启并验证：

```bash
launchctl kickstart -k gui/$(id -u)/com.cliproxyapi
curl -s -m 8 http://127.0.0.1:8317/v1/models \
  -H "Authorization: Bearer $(head -1 ~/.cliproxyapi/.keys)" | head -c 300
```

### 3.2 Codex（CLIProxyAPI，端口 8327）

同一份配置思路，只是文件不同：`~/.cliproxyapi/config-codex.yaml` 同样加 `proxy-url`，然后：

```bash
launchctl kickstart -k gui/$(id -u)/com.cliproxyapi.codex
```

### 3.3 Grok Build（端口 8080）

编辑 `~/.grokbuild-proxy/config.yaml` 的 `proxy` 段（注意是结构化的，不是单个 URL）：

```yaml
# mode: environment（读环境变量，launchd 下等于没有）| direct（强制直连）| url（走指定代理）
proxy:
  mode: url
  url: "socks5://127.0.0.1:7890"
```

然后：

```bash
launchctl kickstart -k gui/$(id -u)/com.grokbuild.proxy
curl -s http://127.0.0.1:8080/readyz
```

### 3.4 配完之后

- 三条代理链路自检：`python3 scripts/bridge.py status`
- 真实请求验证（比 /models 更能暴露网络问题）：

```bash
# Grok
curl -s -m 30 -X POST http://127.0.0.1:8080/v1/messages \
  -H "Authorization: Bearer <你的 grok api_key>" -H 'Content-Type: application/json' \
  -d '{"model":"grok-4.7","max_tokens":32,"messages":[{"role":"user","content":"hi"}]}'
```

---

## 4. 判断「网络问题」还是「凭据问题」

两者症状都可能是请求失败，但处置完全不同：

| 观察 | 网络问题 | 凭据/冷却问题 |
| :--- | :--- | :--- |
| 代理服务日志 | `dial tcp ... i/o timeout` / `context deadline exceeded` | `401 unauthorized` / `no usable upstream credentials` |
| `/v1/models` | 仍能返回（它不打上游） | 仍能返回 |
| 真实请求 | 超时、5xx 且重试无变化 | Grok 冷却期全 503，约 5 分钟自愈（见 README 6.10） |
| 处置 | 配 `proxy-url` / `proxy.mode: url` | 等待自愈或按 README 6.4 重新授权 |

日志位置：
- Grok：`~/.grokbuild-proxy/proxy.log`
- Gemini / Codex：`~/.cliproxyapi/` 下对应日志（`config.yaml` 的 `logging-to-file: true`）
