# Antigravity (Gemini) 接入 ZCode 深度指南

## 1. 组件概述

**CLIProxyAPI** 是一个通用的本地 AI 代理网关，可桥接各大云服务平台的 OAuth 认证会话，并对外暴露标准 OpenAI / Anthropic 规范接口。
在本项目中，CLIProxyAPI 专门用于桥接 **Google Antigravity**（基于 Google Cloud Code PA 后端 `cloudcode-pa.googleapis.com`），将 Gemini 3.x 系列最新模型引入 ZCode。

- **监听地址**：`127.0.0.1:8317`
- **上游地址**：`https://cloudcode-pa.googleapis.com`
- **服务托管**：macOS `launchd`（`com.cliproxyapi`）
- **程序目录**：`~/.cliproxyapi/`
- **管理后台**：`http://127.0.0.1:8317/management.html`
- **协议暴露**：同时支持 OpenAI 格式与 Anthropic Messages 格式（`/v1/messages`）

---

## 2. 授权认证与多账号管理

### 2.1 Google OAuth 登录流程
CLIProxyAPI 支持通过网页交互登录 Google 账号并自动换取 Antigravity 专用的 OAuth Refresh Token。
1. 终端执行登录：
   ```bash
   cd ~/.cliproxyapi
   ./cli-proxy-api -config config.yaml -antigravity-login
   ```
2. 浏览器弹出 Google 登录界面，授权并完成回调。
3. 凭据文件保存在 `~/.cliproxyapi/auth/antigravity-<邮箱>.json` 中。
4. CLIProxyAPI 内置自动化刷新循环，在 Access Token 即将过期前 5 分钟自动更新，无需人工干预。

### 2.2 本地 API Key 体系
位于 `~/.cliproxyapi/.keys`，包含：
- 第一行：CPA API Key（`sk-cpa-...`），配置在 ZCode 中作为访问凭据。
- 第二行：Management Key（`sk-mgmt-...`），用于访问 Web 管理后台。

---

## 3. 模型列表与显示名映射

CLIProxyAPI 上游会列出一整串 Gemini / Claude 变体。当前 ZCode 里**只保留 3 个**，其余写入 `deletedModels`，避免刷新时再冒出来：

| 模型 ID (Wire) | ZCode 显示名称 | 思考预算上限 | 模态支持 | 典型用途 |
| :--- | :--- | :--- | :--- | :--- |
| `gemini-3.8-flash-high` | Gemini 3.8 Flash | 65,535 | 文本 / 多模态 | 日常编码首选 |
| `gemini-3.7-flash-high` | Gemini 3.7 Flash | 65,535 | 文本 / 多模态 | 次世代 Flash 稳定版 |
| `gemini-pro-agent` | Gemini 3.1 Pro | 65,535 | 文本 / 多模态 | **最强推理旗舰** |

> **关键优化说明**：
> 1. 原账号下的 `gemini-3.1-pro-low` 模型被剔除，因其上游强制锁定 Low 档思考，无法调高。
> 2. `gemini-pro-agent` 在官方目录中即为「Gemini 3.1 Pro (High)」，重命名为 `Gemini 3.1 Pro` 便于在 ZCode 列表中直观选取。
> 3. 账号内包含的 `claude-opus-4-6-thinking`、`claude-sonnet-4-6` 等未接入，保持纯粹专注于 Gemini。

---

## 4. 自动化注入与 ZCode 注册

执行脚本：
```bash
python3 scripts/apply-gemini-provider.py
```
该脚本具有以下特性：
- **幂等性**：多次执行会自动更新模型配置与时间戳，不会产生重复脏数据。
- **自动备份**：修改前自动将原配置备份至 `~/.zcode/v2/config.json.bak-antigravity`。
- **动态读取 Key**：自动从 `~/.cliproxyapi/.keys` 读取最新的 Bearer Token。
- **配置 Thinking**：统一赋予各模型 Low (4096) / Medium (16384) / High (60000) 真实生效的 reasoningSpec。

---

## 5. 常用运维与故障排查

### 5.1 快速健康检查
```bash
# 获取已注册模型列表
curl -s http://127.0.0.1:8317/v1/models \
  -H "Authorization: Bearer $(head -1 ~/.cliproxyapi/.keys)" | jq .

# 检查日志
tail -f ~/.cliproxyapi/server.log
```

### 5.2 重启服务
```bash
launchctl kickstart -k gui/$(id -u)/com.cliproxyapi
```

### 5.3 凭据失效处理
如果日志显示 Google 鉴权失败或 Refresh Token 失效：
```bash
cd ~/.cliproxyapi
./cli-proxy-api -config config.yaml -antigravity-login
launchctl kickstart -k gui/$(id -u)/com.cliproxyapi
```
重新登录成功后代理立即恢复，ZCode 端无需改动即可继续使用。

### 5.4 网络环境要求（受限网络必读）

本通道的上游是 **`cloudcode-pa.googleapis.com`**（Google Cloud Code PA 后端），在大陆网络下无法直连。先自测：

```bash
curl -s -o /dev/null -w '%{http_code}\n' -m 5 https://cloudcode-pa.googleapis.com
# 返回 403/404 都算通（那是服务器在应答）；超时/拒绝 = 需要代理
```

**最常见的坑**：CLIProxyAPI 由 launchd 托管，**不读终端的 `HTTP_PROXY`，也不读 macOS 系统代理**。
即使 Clash 开了系统代理，ZCode 里的 Gemini 请求仍会超时——代理只覆盖了 ZCode → 本地 8317 这一段，
本地 → Google 那一段还是裸连。

**解法**：把代理写进 `~/.cliproxyapi/config.yaml` 顶层：

```yaml
proxy-url: "socks5://127.0.0.1:7890"   # 支持 socks5/http/https，换成你的实际代理
```

然后 `launchctl kickstart -k gui/$(id -u)/com.cliproxyapi` 重启生效。

> 例外：代理 App 开了 TUN/增强模式（虚拟网卡接管全局路由）时无需配置，
> `route -n get default` 显示 `utun*` 接口即属于这种形态。

网络问题与凭据问题的区分方法、其余通道的代理配置，统一见 **[docs/network-environment.md](network-environment.md)**。

### 5.5 上游模型目录里的「假 Claude」
`/v1/models` 会列出 `claude-opus-4-6-thinking`、`claude-sonnet-4-6` 等条目——那是 Antigravity 账号附带的
Claude 变体，不是独立的真 Claude 通道。本项目未接入它们（保持 Gemini 专一），ZCode 里不会出现。
