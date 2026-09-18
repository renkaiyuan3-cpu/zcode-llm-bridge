# 本地代理巡检 / 重启 / 日志。包装 scripts/bridge.py。
# 用法:
#   powershell -ExecutionPolicy Bypass -File .\windows\service-manager.ps1 status
#   powershell -ExecutionPolicy Bypass -File .\windows\service-manager.ps1 restart
#   powershell -ExecutionPolicy Bypass -File .\windows\service-manager.ps1 logs
param(
    [Parameter(Position = 0)]
    [ValidateSet("status", "restart", "restart-grok", "restart-gemini", "restart-codex", "logs", "doctor")]
    [string]$Command = "status"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Bridge = Join-Path $RepoRoot "scripts\bridge.py"

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @("py", "-3") }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @("python") }
    throw "找不到 Python 3。请安装并勾选 Add python.exe to PATH。"
}

$Python = Find-Python
$PyArgs = @($Python | Select-Object -Skip 1)
$Args = switch ($Command) {
    "status" { @("status") }
    "logs" { @("logs") }
    "doctor" { @("doctor") }
    "restart" { @("restart", "all") }
    "restart-grok" { @("restart", "grok") }
    "restart-gemini" { @("restart", "gemini") }
    "restart-codex" { @("restart", "codex") }
}

& $Python[0] @PyArgs $Bridge @Args
exit $LASTEXITCODE
