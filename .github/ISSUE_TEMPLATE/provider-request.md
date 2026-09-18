---
name: 新供应商提议
about: 想让某个新的订阅 / API 通道接入 ZCode
title: "[Provider] "
labels: enhancement
assignees: ""
---

**上游是什么**
<!-- 服务商 / 订阅名称，官方 API 文档或客户端 -->

**协议类型**
Anthropic Messages（`/v1/messages`）还是 OpenAI Chat Completions？不确定的话贴一次抓包/报错。

**思考档位实测**
<!-- 本项目最看重这一项：上游真实接受的档位取值域是什么？有没有实测证据？
     参考：Codex 目录里写了 ultra 但实测拒收；Command Code 不接受 off。
     请附上你实测的请求与响应（脱敏后）。 -->

**其他已知限制**
<!-- 模态支持（PDF？图片？）、上下文/输出上限、计费陷阱、风控行为…… -->

**你愿意提 PR 吗**
按 CONTRIBUTING.md 的「如何新增一个供应商」走一遍即可，文档写清楚是最大的贡献。
