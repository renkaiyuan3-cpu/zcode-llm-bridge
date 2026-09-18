# OpenCode Go 接入 ZCode

## 1. 目标

只用 OpenCode Go 订阅里的 **DeepSeek V4.1 Flash**，接到 ZCode 自定义供应商。不走本地代理，直连官方 API。

- **供应商 ID**：`opencode-go`
- **显示名**：OpenCode Go
- **模型 ID**：`deepseek-v4.1-flash`
- **协议**：OpenAI Compatible Chat Completions
- **Base URL**：`https://opencode.ai/zen/go/v1`
- **实际请求**：`POST https://opencode.ai/zen/go/v1/chat/completions`

官方文档：[OpenCode Go](https://opencode.ai/docs/zh-cn/go/)。ZCode 在官方兼容客户端名单里。

## 2. 为什么不是 Anthropic 协议

DeepSeek V4.1 Flash 在 Go 目录里走的是 `@ai-sdk/openai-compatible`，不是 `/v1/messages`。MiniMax / Qwen 才走 Anthropic Messages。

ZCode 对 openai-compatible 的思考注入不是 `thinking.budget_tokens`，而是：

```json
{ "reasoning_effort": "high" }
```

所以本供应商的 `reasoningSpec` 写成：

```json
{
  "defaultLevel": "high",
  "levels": {
    "high": {
      "openai-compatible": {
        "set": [{ "path": ["reasoningEffort"], "value": "high" }]
      }
    }
  }
}
```

`off` 会映射成 `none`。档位：`off / low / medium / high / xhigh / max`，默认 `high`。

## 3. 认证与请求头

- API Key 存在本机：`~/.opencode-go/api_key`（权限 600），不进 Git。
- 也可用环境变量 `OPENCODE_GO_API_KEY`。
- 官方要求流量看起来像编码 Agent：
  - `User-Agent: ZCode`
  - `x-opencode-session: zcode-opencode-go-local`（稳定会话 ID，便于路由和缓存）

## 4. 一键注入

```bash
python3 scripts/apply-opencode-go-provider.py
```

脚本会：

1. 读本机 Key，写进 `~/.zcode/v2/config.json` 的 `opencode-go`
2. 只保留 `deepseek-v4.1-flash`
3. 把其余常见 Go 模型写进 `deletedModels`，避免刷新时冒出来
4. 写入 UI 档位 + `reasoningSpec` + `zcode.reasoning`

改 Key 后重新跑一次脚本即可。

## 5. 连通性实测

2026-09-16 用当前订阅实测：

```
POST /zen/go/v1/chat/completions
model=deepseek-v4.1-flash
reasoning_effort=low
HTTP 200
usage.completion_tokens_details.reasoning_tokens=14
```

接口可用，思考字段会被上游统计。

## 6. 注意

- Go 是按美元额度限流（5 小时 / 周 / 月），不是经典 RPS。
- 一个 workspace 只应有一个 Go 订阅者。
- ZCode 重启仍可能剥掉顶层 `reasoningSpec`。靠 `scripts/restore-reasoning.py` 每分钟补回。
