# Windows 接入指南

ZCode 官方客户端支持 Windows。本仓库的注入脚本是纯 Python，**配置路径与 macOS 相同**：`%USERPROFILE%\.zcode\v2\config.json`。差别只在「谁负责把代理和自愈任务变成开机自启」——Windows 用**任务计划程序**，对应 macOS 的 launchd。

> 还没装过？先跑体检，它会用中文告诉你缺哪一步：
>
> ```powershell
> py -3 scripts\bridge.py doctor
> ```

## 0. 前置

| 需要 | 说明 |
| :--- | :--- |
| [ZCode](https://z.ai) Windows 客户端 | **至少成功启动过一次**，否则没有 `config.json`，注入脚本会直接拒绝写入 |
| Python 3.9+ | 从 [python.org](https://www.python.org/downloads/windows/) 安装，**勾选 Add python.exe to PATH**。安装后新开一个 PowerShell，`py -3 --version` 能出号即可 |
| Git（可选） | 用来 `git clone`；也可以 GitHub 网页 Download ZIP |

SmartScreen 可能拦截从 GitHub 下载的 `.exe`：选「更多信息 → 仍要运行」。本仓库**不附带**这些二进制，它们来自上游 Releases。

## 1. 最快路径（2 分钟，无需本地代理）

Command Code / OpenCode Go 是直连官方 API，Windows 和 Mac 步骤完全一样。

```powershell
git clone https://github.com/renkaiyuan3-cpu/zcode-llm-bridge.git
cd zcode-llm-bridge

# Command Code
New-Item -ItemType Directory -Force $env:USERPROFILE\.commandcode | Out-Null
Set-Content -Encoding utf8 $env:USERPROFILE\.commandcode\api_key "sk-你的Key"

py -3 scripts\apply-commandcode-provider.py
py -3 scripts\bridge.py install restore
```

OpenCode Go 同理：`%USERPROFILE%\.opencode-go\api_key` + `scripts\apply-opencode-go-provider.py`。

然后**重启 ZCode**，模型选择器里应出现对应分组。自愈任务每 1 分钟检查一次 `reasoningSpec`（任务计划程序的最小重复间隔是 1 分钟；macOS launchd 是 60 秒，效果等价）。

验收：

1. `py -3 scripts\bridge.py doctor` 里 ZCode 配置为 ✅，自愈任务 `ZCodeLLMBridge.RestoreReasoning` 为 ✅。
2. ZCode 里能看到供应商；发一条「用一句话介绍你自己」能回复。
3. 切 High / Low 各发一道推理题，High 应明显更「想得久」。若两档无差别，看第 6 节。

## 2. 订阅 OAuth → 本地代理（Grok / Gemini / Codex）

本地代理的二进制**不是本仓库的一部分**。Windows 包在上游 Releases 里：

| 组件 | 上游 | Windows 包名（x64） |
| :--- | :--- | :--- |
| CLIProxyAPI（Gemini / Codex） | [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI/releases) | `CLIProxyAPI_*_windows_amd64.zip` |
| grokbuild-proxy（Grok Build） | [GreyGunG/grokbuild-proxy](https://github.com/GreyGunG/grokbuild-proxy/releases) | `grokbuild-proxy_Windows_x86_64.zip` |

ARM64 机器选 `windows_aarch64` / `Windows_arm64`。

### 2.1 一键下载（推荐）

```powershell
py -3 scripts\bridge.py fetch
# 或: powershell -ExecutionPolicy Bypass -File .\windows\fetch-binaries.ps1
```

会把 `cli-proxy-api.exe` 放到 `%USERPROFILE%\.cliproxyapi\`，把 `grokbuild-proxy.exe` 放到 `%USERPROFILE%\.grokbuild-proxy\`。

### 2.2 Gemini（Antigravity 订阅）

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\.cliproxyapi | Out-Null
Copy-Item templates\cliproxyapi-gemini.example.yaml $env:USERPROFILE\.cliproxyapi\config.yaml
cd $env:USERPROFILE\.cliproxyapi
.\cli-proxy-api.exe -config config.yaml -antigravity-login
cd -
# 回到仓库目录
py -3 scripts\bridge.py install gemini
py -3 scripts\apply-gemini-provider.py
```

浏览器会弹出 Google 登录。凭据落在 `%USERPROFILE%\.cliproxyapi\auth\`，本地 API Key 在 `.keys`。

### 2.3 Codex（ChatGPT 订阅）

Windows **优先用 CPA 自己的登录**拿独立凭据，不要和 ChatGPT 桌面端共用 refresh_token（会互踢）：

```powershell
Copy-Item templates\cliproxyapi-codex.example.yaml $env:USERPROFILE\.cliproxyapi\config-codex.yaml
cd $env:USERPROFILE\.cliproxyapi
.\cli-proxy-api.exe -config config-codex.yaml -codex-login
cd -
py -3 scripts\bridge.py install codex
py -3 scripts\apply-codex-provider.py
```

若你已经用过 Codex CLI、本机有 `%USERPROFILE%\.codex\auth.json`，也可以扁平化导入（格式不对会「1 个账号、0 个模型」）：

```powershell
py -3 scripts\import-codex-auth.py
```

### 2.4 Grok Build

```powershell
New-Item -ItemType Directory -Force $env:USERPROFILE\.grokbuild-proxy | Out-Null
Copy-Item templates\grokbuild-proxy.example.yaml $env:USERPROFILE\.grokbuild-proxy\config.yaml
cd $env:USERPROFILE\.grokbuild-proxy
.\grokbuild-proxy.exe -device-login
cd -
py -3 scripts\bridge.py install grok
py -3 scripts\apply-grok-provider.py
```

设备码登录会打印 URL 和码，用浏览器完成绑定。**不要**复用官方 Grok CLI 的 `~\.grok` 凭据。

最后同样要装自愈：

```powershell
py -3 scripts\bridge.py install restore
py -3 scripts\bridge.py status
```

## 3. Windows 计划任务对照

| 任务名 | 作用 | macOS 对应 |
| :--- | :--- | :--- |
| `ZCodeLLMBridge.RestoreReasoning` | 每 1 分钟幂等补回 `reasoningSpec` | `com.zcode.restore-reasoning` |
| `ZCodeLLMBridge.GrokProxy` | 登录后拉起 grokbuild-proxy :8080 | `com.grokbuild.proxy` |
| `ZCodeLLMBridge.GeminiProxy` | 登录后拉起 CLIProxyAPI :8317 | `com.cliproxyapi` |
| `ZCodeLLMBridge.CodexProxy` | 登录后拉起 CLIProxyAPI :8327 | `com.cliproxyapi.codex` |

查看：`Win + R` → `taskschd.msc`，任务计划程序库里搜 `ZCodeLLMBridge`。

命令行：

```powershell
py -3 scripts\bridge.py status
py -3 scripts\bridge.py restart grok
py -3 scripts\bridge.py logs
py -3 scripts\bridge.py uninstall          # 卸掉本项目注册的全部任务
```

**关键坑：默认 72 小时时限。** 任务计划程序新建任务若不把「停止超过以下时间的任务」关掉，代理会在 3 天后被静默杀掉。`bridge.py install` 已把 `ExecutionTimeLimit` 设为 0。如果你是手工在 GUI 里建的任务，请勾掉该选项。

代理任务是「用户登录时」触发 + 失败后 1 分钟重启 3 次。自愈任务额外每 1 分钟重复一次。

## 4. 路径速查

| 用途 | 路径 |
| :--- | :--- |
| ZCode 配置 | `%USERPROFILE%\.zcode\v2\config.json` |
| 自愈运行时副本 | `%USERPROFILE%\.zcode-proxy\` |
| Grok 代理 | `%USERPROFILE%\.grokbuild-proxy\` |
| CLIProxyAPI | `%USERPROFILE%\.cliproxyapi\` |
| Command Code Key | `%USERPROFILE%\.commandcode\api_key` |
| OpenCode Go Key | `%USERPROFILE%\.opencode-go\api_key` |

注入脚本里写的是 `~/.zcode/...`，Python 在 Windows 上会展开成上面这些路径，**不要改脚本去写 `%USERPROFILE%`**。

## 5. 和 macOS 不同的坑

1. **Python 启动器是 `py -3`，不是 `python3`。** 没勾选 PATH 时，Win + R 能打开商店占位符 `python.exe`，一跑就去 Microsoft Store。用 `py -3` 可避开。
2. **执行策略。** 直接跑 `.ps1` 可能被拦：`powershell -ExecutionPolicy Bypass -File .\windows\install-runtime.ps1`。只跑 `py -3 scripts\bridge.py ...` 则不受影响。
3. **没有 TCC 桌面拦截。** 仓库放桌面也可以。不过自愈任务读的仍是 `%USERPROFILE%\.zcode-proxy\` 里的副本——改完 `scripts\` 后必须再跑一次 `bridge.py install restore`，否则计划任务还在跑旧文件。
4. **防火墙。** 监听 `127.0.0.1` 通常不弹窗。若弹了，允许专用网络即可，不要勾「公用网络」。
5. **Codex 没有 `/Applications/ChatGPT.app/...` 那条路径。** 用 `-codex-login`，或导入 `%USERPROFILE%\.codex\auth.json`。
6. **日志。** 代理 stdout 由上游自己写文件（`server.log` / `proxy.log`）。计划任务的「历史记录」默认是关的，查问题优先看这些日志文件，而不是任务计划程序。

## 6. 故障排除

| 现象 | 处理 |
| :--- | :--- |
| `找不到 ZCode 配置` | 先启动一次 ZCode |
| 计划任务在，端口没在听 | `py -3 scripts\bridge.py restart grok`（或 gemini/codex）；看对应 `.err.log` / `proxy.err.log` |
| `/v1/models` 0 个模型（Codex） | 凭据不是扁平 + `type: codex`，跑 `import-codex-auth.py` 或改用 `-codex-login` |
| 档位 High/Low 无差别 | `reasoningSpec` 被剥掉。确认 `ZCodeLLMBridge.RestoreReasoning` 在、且 `%USERPROFILE%\.zcode-proxy\restore-reasoning.py` 存在 |
| SmartScreen / 杀软拦截 exe | 上游 Go 二进制无签名，加白名单或「仍要运行」 |
| `py` 不是内部或外部命令 | 重装 Python，勾选 PATH，**新开** PowerShell |

通用通道的坑（档位取值域、Token 互踢、272K 计价）与 macOS 相同，见 README 第 6 节和各 `docs/*-guide.md`。
