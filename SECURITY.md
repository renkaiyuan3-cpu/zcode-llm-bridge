# Security Policy

## 这个项目会碰到什么秘密

运行时会出现三类敏感数据，**它们不属于本仓库，也永远不该被提交或贴到 Issue**：

- 上游 OAuth：`~/.cliproxyapi/auth/`、`~/.cliproxyapi/auth-codex/`、`~/.grokbuild-proxy/data/`
- 本地网关钥匙：`~/.cliproxyapi/.keys`、`~/.cliproxyapi/.keys-codex`、`~/.grokbuild-proxy/data/meta.json`
- ZCode 配置里的 `apiKey`：`~/.zcode/v2/config.json`（以及直连通道的 `~/.commandcode/api_key`、`~/.opencode-go/api_key`）

Windows 下 `~` 就是 `%USERPROFILE%`。

## 如何报告漏洞

请使用 GitHub 的 **Privately report a vulnerability**：

https://github.com/renkaiyuan3-cpu/zcode-llm-bridge/security/advisories/new

适合走这条通道的包括：

- 脚本把密钥写进世界可读文件、或打进日志 / 崩溃报告
- 路径拼接 / 临时文件可被他人抢写（本机多用户）
- 文档或模板里残留真实凭据、个人绝对路径
- 计划任务 / launchd 以过高权限运行、或监听了非回环地址

**不要**在公开 Issue 里贴 `auth.json`、`.keys`、`config.json` 原文。贴日志前先打码 `sk-`、`Bearer`、`refresh_token`、`access_token`。

## 不在范围内

- 上游（xAI / Google / OpenAI / Z.ai 等）自己的风控、封号、ToS
- 你把订阅额度转给第三方使用造成的损失（见 [DISCLAIMER.md](DISCLAIMER.md)）
- 「帮我过验证码 / 绕过限流」类请求

## 修复预期

这是个人维护的社区项目。确认后会尽量在合理时间内打补丁并轮换已泄露的模板占位符；不会公开完整利用步骤。
