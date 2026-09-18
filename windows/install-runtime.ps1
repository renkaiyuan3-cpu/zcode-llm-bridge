# 把自愈脚本装到 %USERPROFILE%\.zcode-proxy，并注册每分钟补回思考档位的计划任务。
# 用法（在仓库根目录）:
#   powershell -ExecutionPolicy Bypass -File .\windows\install-runtime.ps1
#   powershell -ExecutionPolicy Bypass -File .\windows\install-runtime.ps1 -Target all
param(
    [ValidateSet("restore", "grok", "gemini", "codex", "all")]
    [string]$Target = "restore"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Bridge = Join-Path $RepoRoot "scripts\bridge.py"

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @("py", "-3")
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @("python")
    }
    throw "找不到 Python 3。请从 https://www.python.org/downloads/windows/ 安装，并勾选 Add python.exe to PATH。"
}

$Python = Find-Python
$PyArgs = @($Python | Select-Object -Skip 1)
Write-Host ">> $($Python -join ' ') $Bridge install $Target"
& $Python[0] @PyArgs $Bridge install $Target
exit $LASTEXITCODE
