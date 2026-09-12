param([string]$PythonPath = '')

$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$versionCheck = 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'

if (Test-Path -LiteralPath $projectPython) {
    & $projectPython -c $versionCheck
    if ($LASTEXITCODE -eq 0) {
        Write-Host '项目 Python 环境已就绪。'
        exit 0
    }
    throw '已有 .venv 无法使用，请先检查其来源；脚本不会自动覆盖。'
}

$candidates = @()
if ($PythonPath) {
    $candidates += $PythonPath
} else {
    foreach ($name in @('python', 'python3')) {
        $found = Get-Command $name -CommandType Application -ErrorAction SilentlyContinue
        if ($found -and $found.Source -notlike '*\Microsoft\WindowsApps\*') {
            $candidates += $found.Source
        }
    }
    $launcher = Get-Command py -CommandType Application -ErrorAction SilentlyContinue
    if ($launcher) {
        $resolvedPython = & $launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0) { $candidates += $resolvedPython }
    }
    $candidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}

$selectedPython = $null
foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
    & $candidate -c $versionCheck
    if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
}
if (-not $selectedPython) {
    throw '未找到 Python 3.10+。请使用 -PythonPath 指定可用的 Python 完整路径。'
}

& $selectedPython -m venv --without-pip (Join-Path $PSScriptRoot '.venv')
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败。' }
& $projectPython --version
if ($LASTEXITCODE -ne 0) { throw '虚拟环境校验失败。' }
Write-Host '初始化完成；本项目使用标准库，无需安装 pip 或 npm 依赖。'
