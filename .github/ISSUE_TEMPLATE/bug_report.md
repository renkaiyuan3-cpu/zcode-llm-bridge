---
name: 问题反馈
about: 某个通道接不上 / 报错 / 档位不生效
title: "[Bug] "
labels: bug
assignees: ""
---

<!-- 提交前请先过一遍 README 第 6 节「故障排除速查手册」，很多问题有现成答案 -->

**哪个通道**
Grok Build / Antigravity Gemini / Codex / OpenCode Go / Command Code / 自愈任务

**现象**
<!-- 你做了什么、期望什么、实际发生了什么 -->

**报错原文**
```
<!-- 粘贴完整报错，不要截图代码块 -->
```

**环境**
- macOS 版本：
- ZCode 版本：
- CLIProxyAPI / grokbuild-proxy 版本（如涉及）：

**日志片段**
```bash
# 对应通道的日志，注意先脱敏（抹掉 token / api key）
tail -50 ~/.cliproxyapi/server.err.log    # 或 proxy.err.log / codex-server.err.log
```

**已尝试的排查**
<!-- 比如：重跑 apply 脚本、重启代理、检查 LastExitStatus…… -->
