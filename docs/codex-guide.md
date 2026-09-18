# Codex（ChatGPT 订阅）接入 ZCode

## 1. 目标

把 ChatGPT 订阅里的 4 个 GPT 模型接到 ZCode 自定义供应商，分组名 **Codex**。

- **供应商 ID**：`codex-local`
- **显示名**：Codex
- **模型**：`gpt-6-astra`、`gpt-5.6-sol`、`gpt-5.6-terra`、`gpt-5.6-luna`
- **协议**：OpenAI Compatible Chat Completions
- **Base URL**：`http://127.0.0.1:8327/v1`
- **实际请求**：`POST http://127.0.0.1:8327/v1/chat/completions`

## 2. 先厘清：Codex 的终端版在哪

Codex **没有独立安装的 CLI**，它捆绑在 ChatGPT.app 内部：

```
/Applications/ChatGPT.app/Contents/Resources/codex     # Mach-O arm64, codex-cli 0.154.0-alpha.6.2
```

它不在 `PATH` 里，但可以直接全路径调用，功能完整（`exec` / `review` / `mcp` / `app-server` / `resume` 等），还有一个未写进 `--help` 的隐藏命令 `responses-api-proxy`。

**但本方案不用它做转发**。它是个 Agent，不是模型 API 服务器；`app-server` 是给桌面端用的 JSON-RPC 控制通道，不是 LLM 接口。真正把订阅变成模型 API 的是 CLIProxyAPI。

### 顺带结论：ZCode 没有内置 Codex 通道

ZCode 的 `enabledBuiltinAgentCliProviders` 配置项，从 `app.asar` 里挖出的定义是：

```js
ii=["glm"]
```

合法值只有 `glm` 一个。**内置 Agent CLI 只支持 GLM**，没有任何 Codex / Grok / Gemini 通道。本仓库里所有自定义供应商，本质都是「本地代理 + 自定义 provider」拼出来的。

## 3. 架构

```
ZCode (自定义 provider: Codex, openai-compatible)
   │  POST /v1/chat/completions   http://127.0.0.1:8327/v1
   ▼
CLIProxyAPI (本机 127.0.0.1:8327, 由 launchd 托管)
   │  OAuth 自动刷新
   ▼
ChatGPT 后端（https://chatgpt.com/backend-api/codex/responses）
```

与 Antigravity Gemini 那套**完全隔离**：独立端口、独立凭据目录、独立 API Key。互不影响，Gemini 那边的模型列表也不会被 Codex 模型污染。

| 项目 | 路径 |
|---|---|
| 主程序 | `~/.cliproxyapi/cli-proxy-api`（与 Gemini 共用同一个二进制） |
| 配置 | `~/.cliproxyapi/config-codex.yaml` |
| 凭据 | `~/.cliproxyapi/auth-codex/codex-<邮箱>.json` |
| API Key | `~/.cliproxyapi/.keys-codex` |
| 运行日志 | `~/.cliproxyapi/codex-server.log` / `.err.log` |
| launchd | `~/Library/LaunchAgents/com.cliproxyapi.codex.plist` |
| ZCode provider 脚本 | `scripts/apply-codex-provider.py` |

## 4. 凭据：如何把 `~/.codex/auth.json` 导入 CPA

**这是本次接入最关键的一点**，也是踩过的坑。

CPA 的账号文件是**扁平结构**，必须带 `type: "codex"`：

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "account_id": "...",
  "email": "you@example.com",
  "expired": "2026-09-20T03:19:18-07:00",
  "last_refresh": "2026-09-10T10:19:14.984068Z",
  "type": "codex"
}
```

**直接把 `~/.codex/auth.json` 原样复制过去是不行的**——那份是 `{"auth_mode", "tokens": {...}}` 的嵌套结构，CPA 会读进来但归类不了，日志里表现为 `1 auth entries` 却 `0 个模型`，静默失败。

导入命令（`expired` 从 access_token 的 JWT `exp` 解析，不要手写）：

```bash
python3 - <<'PY'
import json, base64, datetime, os
src = json.load(open(os.path.expanduser("~/.codex/auth.json")))
t = src["tokens"]
p = t["access_token"].split(".")[1]; p += "=" * (-len(p) % 4)
exp = datetime.datetime.fromtimestamp(json.loads(base64.urlsafe_b64decode(p))["exp"]).astimezone()
q = t["id_token"].split(".")[1]; q += "=" * (-len(q) % 4)
email = json.loads(base64.urlsafe_b64decode(q)).get("email", "unknown")
out = {
    "access_token": t["access_token"], "refresh_token": t["refresh_token"],
    "id_token": t["id_token"], "account_id": t["account_id"],
    "email": email, "expired": exp.isoformat(),
    "last_refresh": src.get("last_refresh"), "type": "codex",
}
dst = os.path.expanduser(f"~/.cliproxyapi/auth-codex/codex-{email}.json")
os.makedirs(os.path.dirname(dst), exist_ok=True)
json.dump(out, open(dst, "w"), indent=1); os.chmod(dst, 0o600)
print("导入完成:", dst)
PY
```

### ⚠️ 刷新令牌轮换风险

`~/.codex/auth.json` 的 access_token 有效期约 **10 天**。CPA 与 Codex CLI／桌面端**共用同一份 refresh_token**，谁先刷新都可能让对方那份失效——和 Grok Build 单次轮换互踢是同一类问题。

- 现状：导入的是同一份凭据，两边同时活跃时可能互相踢下线。
- 失效表现：CPA 日志出现 `refresh` 相关报错，ZCode 里请求 401。
- 立即恢复：重跑上面的导入命令（Codex CLI 会先把 auth.json 刷新到最新）。
- 根治方案：让 CPA 走自己的 `./cli-proxy-api -codex-login` 拿一份独立凭据（需要浏览器授权），之后互不干扰。

## 5. 思考档位：真实取值域是 5 档，不是 6 档

模型目录（`codex debug models`）里 `gpt-6-astra` / `gpt-5.6-sol` / `gpt-5.6-terra` 都列了 6 档，含 `ultra`：

```
supported_reasoning_levels: low, medium, high, xhigh, max, ultra
```

**但 CPA 会直接拒掉 `ultra`**：

```
HTTP 400  level "ultra" not supported, valid levels: low, medium, high, xhigh, max
```

所以档位只能写 5 个。这正是 README 第 2.4 节说的「假档位的第二种变体：取值域不合法」——**模型目录里写了不等于上游接受，必须实测**。

档位注入走 `reasoning_effort`（不是 Anthropic 的 `thinking`）：

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

## 6. 推理速度档：实测接不进来

模型目录标了速度档：

| 模型 | 速度档 |
|---|---|
| `gpt-6-astra` | `priority`（Fast，2x 速度，消耗更快） |
| `gpt-5.6-sol` | `priority`（1.5x）、`ultrafast` |
| `gpt-5.6-terra` / `-luna` | `priority`（1.5x） |

Codex CLI 的 `fast_mode` 特性也是 `stable / true`。**但在 Plus 订阅下不生效**，实测证据：

1. 经 CPA 发 `service_tier: "priority"`，响应回显恒为 `"default"`。
2. **绕过 CPA 直接打 `chatgpt.com/backend-api/codex/responses`**（用同一个 OAuth token），`service_tier` 传 `default` / `priority` / `ultrafast` 三种值，回显**全部是 `"default"`**。

第 2 条是关键：它排除了「CPA 把字段吞了」的可能——是**后端按账号档位直接忽略**。

另外 `reasoning.mode` 只接受 `standard` 和 `pro` 两个值，且对这批模型报 `` `reasoning.mode` is not supported with this model ``。

**结论：速度档是账号级限制，接不进来。** 因此脚本里**没有**暴露速度档——加了就是一条永远不生效的假档位，比不加更糟。

## 7. 一键注入

```bash
python3 scripts/apply-codex-provider.py
```

脚本会：

1. 读 `~/.cliproxyapi/.keys-codex`，写进 `~/.zcode/v2/config.json` 的 `codex-local`
2. 只保留 4 个模型（astra / sol / terra / luna）
3. 把其余 7 个写进 `deletedModels`（`gpt-5.5`、`codex-auto-review`、6 个 `gpt-image-*`）
4. 写入 UI 档位 + `reasoningSpec` + `zcode.reasoning`，档位 `low/medium/high/xhigh/max`，默认 `high`

执行后**重启 ZCode 客户端**。

## 8. 上下文窗口：默认 272K，可开到 1M

**默认值是假的。** 模型目录里 `context_window = 272000`，但那只是 Codex 的默认档，不是模型能力上限。

推导链（三处独立证据互相印证）：

1. **官方模型文档**：GPT-5.6 全系（Sol / Terra / Luna）支持 **1,050,000** token 上下文、128K 最大输出。
2. **模型目录**里另有一个 `max_context_window = 872000`。注意 **872000 = 1000000 − 128000**（输出预留）——这个减法说明 1M 是官方开放的可选**总窗口**，872K 是扣掉输出后的输入预算。
3. **OpenAI Codex 工程师 Tibo** 给出的开启方式就是 `model_context_window = 1000000`（原先仅 API Key 可用，2026-08-17 起 ChatGPT 订阅账号同样生效）。

所以本供应商的 4 个模型统一写 `context = 1000000`、`output = 128000`。ZCode 的 `limit.context` 记的是**总窗口**、`output` 单列（与 Command Code 的 `gpt-5.6-luna` 写 1050000 是同一约定）。

### 实测证据

2026-09-16 通过 CPA 发送 **397,606 token** 的输入（`gpt-5.6-luna`）：

```
HTTP 200 | prompt_tokens = 397606 | completion = 20 | 回答 = LONGCTX_OK
```

**已突破 272K 阈值**，证明长上下文通道真实可用，不是纸面参数。

> 说明：验证到 ~400K 为止（再往上会大量消耗订阅额度）。1M 上限依据官方文档与 Codex 自身的 `max_context_window` 推导，未做满量程实测。

### ⚠️ 成本陷阱：272K 是一道计价闸门

**单次请求输入超过 272K 时，上游按 2x 输入 / 1.5x 输出计价，而且乘的是「整个请求」，不是超出部分。** 也就是说 280K 和 800K 的请求走同一个倍率档。

| 模型 | 常规输入 | 超 272K 输入（2x） | 常规输出 | 超 272K 输出（1.5x） |
| :--- | ---: | ---: | ---: | ---: |
| Sol | $5.00/M | $10.00/M | $30.00/M | $45.00/M |
| Terra | $2.50/M | $5.00/M | $15.00/M | $22.50/M |
| Luna | $1.00/M | $2.00/M | $6.00/M | $9.00/M |

订阅用户反馈：开启长上下文后单次高强度使用就可能消耗大量周额度。**建议按任务开，不要当日常默认。**

### 在 Codex 客户端里怎么开

`~/.codex/config.toml` **最开头**（任何 `[section]` 之前）：

```toml
model = "gpt-5.6-sol"
model_context_window = 1000000
model_auto_compact_token_limit = 900000
```

放错位置会被解析成 `expected a boolean` 之类的报错——那是**层级错了，不是数字错了**。

Codex 对这几个值**不做校验**（设 2000000 也照收），它只是拿来做本地压缩决策；真正的上限在服务端。

## 9. 连通性实测

2026-09-16 用当前 Plus 订阅实测，4 个模型 × 2 档位全部 HTTP 200：

| 模型 | 档位 | reasoning_tokens | 响应 |
|---|---|---|---|
| GPT-6-Astra | low / max | 0 / 10 | ✅ |
| GPT-5.6-Sol | low / max | 0 / 0 | ✅ |
| GPT-5.6-Terra | low / max | 0 / 0 | ✅ |
| GPT-5.6-Luna | low / max | 0 / 0 | ✅ |

简单问题（「回 PONG」）不触发思考，`reasoning_tokens=0` 属正常。换真实推理题后档位线性生效：

```
gpt-5.6-sol  同一道题：
  low = 54   medium = 78   high = 83   xhigh = 89   max = 139  (reasoning_tokens)
```

思维链以**摘要**形式回传 `message.reasoning_content`（30+ 字符摘要，非完整思维链；完整 CoT 上游只给加密串）。

## 10. 注意

- **上下文窗口**：`1000000`（总窗口），输出 `128000`。默认的 272K 只是 Codex 的保守值，1M 是官方开放的选项——推导与实测见第 8 节。**注意超 272K 的计价倍率**。
- **输出上限**：目录里 `max_output` 为空，按官方文档填 `128000`。
- ZCode 重启仍可能剥掉顶层 `reasoningSpec`。`scripts/restore-reasoning.py` 已把本供应商加进自愈列表，每分钟补回。
- 新增供应商后**必须重跑** `./scripts/install-runtime.sh`，否则 `~/.zcode-proxy/` 的运行时副本不含新脚本，自愈任务会漏掉它。
