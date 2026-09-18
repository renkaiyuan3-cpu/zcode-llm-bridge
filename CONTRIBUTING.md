# 贡献指南

欢迎 PR！本项目的核心价值是「实测过的坑 + 真实生效的配置」，贡献时请保持这个标准。

## 如何新增一个供应商

这是本仓库最主要的贡献路径（对标 proxypal 的 "Adding a New Agent"）。完整走通一遍大致是：

### 1. 判断协议类型

- 上游是 Anthropic Messages（`/v1/messages`）→ 思考注入走 `thinking.budgetTokens`，用 `lib_zcode_providers.anthropic_reasoning_spec()`。
- 上游是 OpenAI Chat Completions → 思考注入走 `reasoning_effort`，用 `openai_reasoning_spec()`。
- 判断方法：看上游文档，或直接抓一次请求/看报错。

### 2. 实测档位取值域（最重要的一步，不能跳过）

**不要照抄其他供应商的档位列表。** 每家的合法取值域都不同：

- Codex：模型目录里写了 `ultra`，但实测 CPA 拒收 → 只有 5 档；
- Command Code：不接受 `off`/`none`，选中即 HTTP 400；
- Grok：只有 grok-4.6 支持 xhigh。

用最小请求实测（低/高档各发一条推理题，对比 `reasoning_tokens` 是否线性变化），
确认「目录里写的」和「上游真的收的」是两回事。

### 3. 写 `scripts/apply-<name>-provider.py`

以 `apply-grok-provider.py` 为模板，要点：

- **幂等**：重复执行不产生脏数据（用 `ensure_provider` + `apply_reasoning`）；
- **改写前备份**：`backup_cfg(CFG, ".bak-<name>")`；
- **三处写入**：`reasoning`（UI）+ `reasoningSpec`（当前进程）+ `zcode.reasoning`（重启后复活），`apply_reasoning` 已封装；
- **密钥不进仓库**：从本机文件或环境变量读取；
- **tombstone**：订阅里用不到的模型写进 `zcode.deletedModels`，避免刷进模型选择器。

### 4. 登记进自愈任务

把新脚本加进 `scripts/restore-reasoning.py` 的 `SCRIPTS` 列表，否则 ZCode 重启剥掉补丁后它不会被补回。
然后**必须**重跑：

```bash
./scripts/install-runtime.sh
```

（运行时副本在 `~/.zcode-proxy/`，launchd 读的是那份。）

### 5. 文档与表格

- 新增 `docs/<name>-guide.md`（目标结构：目标 → 认证 → 档位实测 → 一键注入 → 已知坑）；
- 更新 README 的「服务对照表」「快速开始」「端口速查表」；
- 如有新端口/launchd 任务，补 plist 模板（用 `__HOME__` 占位符）和 `install-launchd.sh` 分支。

### 6. 提交前自查

- [ ] `grep -rE "sk-[a-zA-Z0-9]{20,}" .` 无真实凭据；
- [ ] 档位取值域经过实测，报错信息注释在脚本里；
- [ ] 文档里的实测日期、证据链完整；
- [ ] `python3 scripts/apply-<name>-provider.py` 重复执行两次输出「已是最新」。

## 其它贡献

- **文档纠错**：上游接口变化导致文档失效，请提 issue 附上报错原文；
- **跨平台**：本项目深度绑定 macOS（launchd / TCC）。Linux（systemd）移植 PR 欢迎，但请保持 macOS 方案为主文档；
- **风格**：中文为主的文档 + 代码注释中文英文皆可；遵循现有文件的语气——重实测证据，轻空泛描述。

## 提交规范

 conventional commits（`feat:` / `fix:` / `docs:` / `chore:`）即可，一个 PR 一件事。
