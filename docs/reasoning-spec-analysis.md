# ZCode 思考模式（Reasoning / Thinking）逆向分析与参数注入规范

## 1. 背景与核心痛点

在将自定义模型接入 ZCode（尤其是通过 Anthropic Messages 协议兼容层）时，开发者普遍会遇到一个**“假思考档位”**问题：
- 在 `~/.zcode/v2/config.json` 的模型定义中配置了：
  ```json
  "reasoning": {
    "variants": ["low", "medium", "high"],
    "defaultVariant": "high"
  }
  ```
- **现象**：ZCode 客户端界面右下角的模型配置面板中，确实出现了 `Low` / `Medium` / `High` 的思考强度切换下拉框。
- **实质**：抓取代理服务收到的 HTTP POST 请求体发现，请求中**根本没有任何 `thinking` 字段或思考预算参数**！
- **后果**：大模型上游要么完全不开启 Extended Thinking，要么按模型默认最低档输出，界面选择纯属摆设。

---

## 2. ZCode 客户端源码逆向分析

通过对 ZCode 核心代码（位于 `out/host/index.js`）的逆向与反混淆分析，揭示了其内部请求构造流程：

### 2.1 调度入口：`applyProviderOptionsPatch`
当用户在前端发起对话请求时，ZCode 会根据当前会话所选模型的配置计算请求选项。
`reasoning` 属性在 ZCode 内部仅作为前端 UI 渲染标记（Schema 提示），而真正驱动 Wire 协议请求补丁的是 **`reasoningSpec`**。

### 2.2 思考请求构造函数：`buildAnthropicThinkingRequest`
逆向提取的核心逻辑伪代码如下：

```javascript
function applyReasoningSpec(requestBody, modelConfig, currentLevel) {
    const spec = modelConfig.reasoningSpec;
    if (!spec || !spec.levels) return;
    
    // 获取当前档位或默认档位
    const levelConfig = spec.levels[currentLevel] || spec.levels[spec.defaultLevel];
    if (!levelConfig || !levelConfig.anthropic) return;

    // 执行 JSON 路径注入
    if (Array.isArray(levelConfig.anthropic.set)) {
        for (const op of levelConfig.anthropic.set) {
            // op.path e.g. ["thinking"]
            // op.value e.g. { "type": "enabled", "budgetTokens": 60000 }
            setNestedPath(requestBody, op.path, op.value);
        }
    }
}
```

### 2.3 关键参数映射与约束规避
1. **命名映射**：
   - 在 `reasoningSpec` 中写入的是驼峰命名的 `budgetTokens`。
   - ZCode 的 Anthropic 协议层在下发到 Wire 协议（HTTP 请求）时，会自动将其转为 Anthropic 标准的蛇形命名：
     ```json
     {
       "thinking": {
         "type": "enabled",
         "budget_tokens": 60000
       }
     }
     ```
2. **`max_tokens` 自动修正**：
   - Anthropic 协议规范严格要求：`budget_tokens < max_tokens`。如果 `budget_tokens >= max_tokens`，服务端会直接报 `HTTP 400 invalid_request_error`。
   - ZCode 检测到 `thinking.budget_tokens` 被注入后，若原先的 `max_tokens` 小于或等于预算，会自动把请求头/体的 `max_tokens` 提升至：
     $$\text{max\_tokens} = \text{budget\_tokens} + 1$$
   - 例如设置 High 档 `budgetTokens: 60000`，下发请求体中的 `max_tokens` 会自动变为 `60001`。

---

## 3. 标准规范配置格式

经过逆向推导，正确使思考档位生效的 `reasoningSpec` 标准配置结构如下：

```json
{
  "reasoningSpec": {
    "defaultLevel": "high",
    "levels": {
      "low": {
        "anthropic": {
          "set": [
            {
              "path": ["thinking"],
              "value": {
                "type": "enabled",
                "budgetTokens": 4096
              }
            }
          ]
        }
      },
      "medium": {
        "anthropic": {
          "set": [
            {
              "path": ["thinking"],
              "value": {
                "type": "enabled",
                "budgetTokens": 16384
              }
            }
          ]
        }
      },
      "high": {
        "anthropic": {
          "set": [
            {
              "path": ["thinking"],
              "value": {
                "type": "enabled",
                "budgetTokens": 60000
              }
            }
          ]
        }
      }
    }
  }
}
```

---

## 3.1 重启后档位丢失的真正原因

ZCode 把内存里的供应商回写成 OpenCode 风格 `config.json` 时：

1. `omitModelCarryoverKeys` 会删掉顶层 `reasoningSpec`
2. `modelProviderModelToOpenCodeModel` 只把 `reasoning` 收成 `{enabled, variants, defaultVariant}`
3. `zcode` 对象里原先手写的 `reasoning` 补丁也会丢

结果：输入框旁边可能还有 Low/High，发出去的请求却没有 `thinking` / `reasoning_effort`。

能熬过一轮回写、启动时又能被读回来的位置是 **`zcode.reasoning`**（完整 `reasoningSpec`）。`openCodeReasoningToModelReasoning` 的优先级是：

1. 顶层 `reasoningSpec`
2. `zcode.reasoning`
3. 只有 variants 的 UI `reasoning`（此时 levels 是空对象，假档位）

所以注入脚本必须同时写三段：`reasoning`（UI）、`reasoningSpec`（当前进程立即生效）、`zcode.reasoning`（重启后复活）。`scripts/restore-reasoning.py` 每分钟检查一次，缺了就补。

openai-compatible 供应商不要套 Anthropic 的 `thinking.budgetTokens`，应写：

```json
"openai-compatible": {
  "set": [{ "path": ["reasoningEffort"], "value": "high" }]
}
```

ZCode 会把它投影成请求体里的 `reasoning_effort`。

## 4. 档位设定标准与实测验证

### 4.1 档位分配推荐值
| 档位 | `budgetTokens` | 适用场景 | 说明 |
| :--- | :--- | :--- | :--- |
| **low** | 4,096 | 简单问答、普通代码补全、快速调试 | 思考速度快，消耗 Token 极少 |
| **medium** | 16,384 | 复杂逻辑分析、重构建议、多模块设计 | 深度思考与速度平衡 |
| **high** | 60,000 | 疑难 Bug 逆向排查、架构级决策、严格推理 | 最大化挖掘 Gemini / Grok 的思维链潜力 |

*(注：部分较早的小模型如 `gemini-3-flash` 预算上限为 `32768`，在注入时取 `min(budget, 32768)`)*

### 4.2 实测验证数据
通过抓包并观察代理服务日志验证：
1. **Low 档请求**：返回推理 token 计数约为 641 tokens。
2. **High 档请求**：返回推理 token 计数达到 2519 ~ 15000+ tokens，模型展开了极其详尽的思维链推导。
3. **Function Calling / Tool Use**：带思考的请求体与 ZCode 的 Tool 调用完全兼容，Anthropic 响应包中先返回 `type: "thinking"` 块，紧接着返回 `type: "tool_use"` 块，ZCode 客户端正常解析并执行工具。
