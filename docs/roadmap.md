# 还能接什么 / 下一步

本仓库的价值不在「再包一层代理」，而在：**把某条已经能说话的 OpenAI / Anthropic 通道，变成 ZCode 里真实生效的思考档位**，并且重启后还在。

新通道请按 [CONTRIBUTING.md](../CONTRIBUTING.md) 走：先测取值域，再写 `apply-*.py`，再登记进 `restore-reasoning.py`。

## 现在就能接、但还没写进仓库的

这些上游要么已经有现成本地代理，要么本身就是 OpenAI Compatible，缺的只是「ZCode 注入 + 档位实测」。

| 候选 | 怎么接 | 为什么值得 | 卡点 |
| :--- | :--- | :--- | :--- |
| **Claude Pro / Max** | CLIProxyAPI 已支持 `-claude-login`，可与 Gemini/Codex 一样再起一个实例 | ZCode 用户最常问的「能不能把 Claude 订阅塞进来」 | 必须独立凭据目录，避免和官方 Claude Code 互踢；档位走 Anthropic `thinking`，要实测 budget 上限 |
| **任意 OpenAI Compatible**（OpenRouter、硅基流动、DeepSeek 官方、Kimi、MiniMax、Qwen…） | 不需要本地代理。ZCode UI 也能手填，但手填没有 `reasoningSpec`，档位是摆设 | 一条 `apply-generic-openai.py` + 环境变量就能覆盖一大片国内 API | **不能照抄档位表**。有的只有 `low/medium/high`，有的把 `off` 映射成 `none` 会 400 |
| **GitHub Copilot** | 参考 [ericc-ch/copilot-api](https://github.com/ericc-ch/copilot-api) 或同类本地桥 | 很多开发者已经付了 Copilot，却没法在 ZCode 里用 | OAuth / device code 流程要隔离；模型列表经常变 |
| **Ollama / 本地模型** | 直连 `http://127.0.0.1:11434/v1` | 无订阅、可离线 | 多数本地模型没有真实 reasoning_effort，不要做假档位 |
| **把本仓库当「反向桥」** | 本地代理已经在听 8080/8317/8327，Cursor / Continue / 其它 Anthropic 客户端也能指向它们 | 推广时很好讲：「ZCode 只是第一个客户」 | 文档要写清楚这不是 ZCode 官方能力 |

不建议做的：把 GLM 再包一层（ZCode 内置已经是 GLM）；做「多账号卖额度」的中转（违反 DISCLAIMER 和第 2 节使用范围）。

## 工程债（比再接一个模型更影响陌生人）

1. **一键安装包** —— `bridge.py fetch` 已经能拉二进制；再往前是 Scoop bucket / `winget` / Homebrew tap，让 Windows 用户不用面对「解压 exe、SmartScreen」。
2. **Linux 一等公民** —— `bridge.py` 已写 systemd --user（beta），缺的是一台 Linux 桌面实机把 ZCode + 代理跑通，把「未实测」标签摘掉。
3. **通用 OpenAI 注入器** —— 避免每家都复制一份 `apply-*.py`；档位列表改成必填参数，强制贡献者写实测证据。
4. **doctor 的 HTTP 探测不要读密钥到 argv** —— 已改用 Python urllib；继续保证 issue 模板强调脱敏。
5. **Windows 实机截图** —— 现在 README 演示全是 macOS。有一张任务计划程序 + ZCode 模型列表的图，Windows 转化率会高很多。

## 文档与社区

- GitHub Discussions：装不上、档位 400、想接新供应商，比 Issue 更适合闲聊。
- `good first issue`：文档里的 macOS 绝对路径、过期模型 ID、英文 README 同步。
- 不要把个人 Desktop 母本里的真实 key / UUID 同步进本仓库。
