# Command Code 接入 ZCode

## 1. 目标

用 Command Code（$10 订阅）里的 **DeepSeek V4.1 Flash** 与 **GPT-5.6 Luna**，接到 ZCode 自定义供应商。不走本地代理，直连官方 API。

| 项 | 值 |
| :--- | :--- |
| **供应商 ID** | `commandcode-local`（可用环境变量 `COMMANDCODE_PROVIDER_ID` 覆盖；若你的 ZCode 里已有 UUID 形态的既有条目，建议沿用旧 ID，避免历史会话 modelRef 失效） |
| **显示名** | Command Code |
| **协议** | OpenAI Compatible Chat Completions |
| **Base URL** | `https://api.commandcode.ai/provider/v1` |
| **实际请求** | `POST https://api.commandcode.ai/provider/v1/chat/completions` |
| **模型 1** | `deepseek/deepseek-v4.1-flash`（显示名 DeepSeek V4.1 Flash，上下文 1,000,000） |
| **模型 2** | `gpt-5.6-luna`（显示名 GPT-5.6 Luna，上下文 1,050,000） |

`/provider/v1/models` 实际返回 **69 个模型**，订阅里远不止这两个。本方案只暴露上面两个，其余 67 个全部写进 `deletedModels`，避免它们刷新时涌进 ZCode 的模型选择器。

## 2. 认证与请求头

- API Key 存在本机：`~/.commandcode/api_key`（权限 600），不进 Git。
- 也可用环境变量 `COMMANDCODE_API_KEY`。
- 显式带上 `User-Agent: ZCode`，与 OpenCode Go 保持一致。

上游走 Cloudflare 前置。短时间内连续打几十个请求会触发 `HTTP 403 {"error code": 1010}`，属于风控限流而非配置错误，隔几秒重试即可恢复。

## 3. 思考档位（这里有个必踩的坑）

Command Code 走 OpenAI 兼容协议，思考参数是 `reasoning_effort`，不是 Anthropic 的 `thinking`。`reasoningSpec` 写成：

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

### 3.1 上游取值域里没有 `off`

实测传 `reasoning_effort: "none"` 会被上游直接拒绝：

```
HTTP 400
Invalid option: expected one of "low"|"medium"|"high"|"xhigh"|"max"
```

而本项目的 `openai_reasoning_spec()` 会把 UI 上的 `off` **映射成 `none`**（见 `lib_zcode_providers.py`）。所以档位里一旦包含 `off`，用户在界面上选中它，发出去的请求必挂 400。

**结论：本供应商档位只能是 `low / medium / high / xhigh / max`，不能有 `off`。**

这也说明「UI 假档位」（README 2.1）还有第二种变体：档位不只是「有没有注入」的问题，**档位取值还必须落进上游的合法域**，否则界面上有、点了就报错。

### 3.2 档位深度实测

2026-09-16 实测，两个模型的档位都真实改变思考深度（同一道多步推理题，非流式）：

| 模型 | `low` | `max` |
| :--- | :--- | :--- |
| `deepseek/deepseek-v4.1-flash` | reasoning_tokens 153 | reasoning_tokens 577 |
| `gpt-5.6-luna` | reasoning_tokens 61 | reasoning_tokens 241 |

`deepseek` 会在响应里返回 `reasoning_content` 字段（思维链原文可直接读到）；`gpt-5.6-luna` 不返回思维链原文，只在 `usage.completion_tokens_details.reasoning_tokens` 里给出思考量。

## 4. 多模态与长度上限

实测结论（都别照抄其他供应商的配置）：

| 能力 | deepseek/deepseek-v4.1-flash | gpt-5.6-luna |
| :--- | :--- | :--- |
| 文本输入 | ✅ | ✅ |
| 图片输入 | ✅（能正确识别颜色） | ✅（能正确识别颜色） |
| PDF 输入 | ❌ HTTP 400 | ❌ HTTP 400 |
| `max_tokens` 上限 | `[1, 393216]` | 实测 800000 仍通过 |
| 流式 SSE | ✅ 含 usage | ✅ 含 usage |

**PDF 不支持**：用 OpenAI 的 `file` 内容类型传 PDF，上游返回
`400 {"message":"Invalid input","param":"messages.0.content"}`。
早期配置里给 DeepSeek 勾了 `pdf`，是错的，已移除。ZCode 侧 `modalities.input` 只保留 `text` + `image`。

## 5. 一键注入

```bash
python3 scripts/apply-commandcode-provider.py
```

脚本会：

1. 读本机 Key（`~/.commandcode/api_key` 或环境变量），写回文件并注入配置；
2. 只保留 `gpt-5.6-luna` 与 `deepseek/deepseek-v4.1-flash`；
3. 修正模态（去掉 pdf）、上下文与输出上限；
4. 写入 UI 档位 + `reasoningSpec` + `zcode.reasoning`（`low/medium/high/xhigh/max`，默认 `high`）；
5. 把其余 67 个模型写进 `deletedModels`；
6. 改写前自动备份到 `~/.zcode/v2/config.json.bak-commandcode`。

脚本已登记进 `scripts/restore-reasoning.py`，每分钟随自愈任务一起幂等重放。

改 Key 后重新跑一次脚本即可。

## 6. 与 ZCode 回写的对抗

ZCode 重启会把顶层 `reasoningSpec` 剥掉（README 第 2 节）。靠 `com.zcode.restore-reasoning` 每分钟补回。

**注意**：该自愈任务曾因 macOS TCC 权限长期静默失败（脚本放在 `~/Desktop` 下，launchd 后台进程读桌面目录报 `Operation not permitted`），导致所有供应商的补丁都处于丢失状态。现已改为从 `~/.zcode-proxy/` 运行时副本执行，用 `scripts/install-runtime.sh` 安装。**改完脚本后要重跑一次 install-runtime.sh，否则运行时副本不会更新。**
