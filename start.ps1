param(
    [ValidateRange(1, 65535)][int]$Port = 8765,
    [ValidatePattern('^[a-f0-9]{16}$')][string]$Project = 'caaaa93ac46840cb',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup.ps1')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$launchArguments = @('-X', 'utf8', '-u', (Join-Path $PSScriptRoot 'team_start.py'), '--port', $Port, '--project', $Project)
if (-not $NoBrowser) { $launchArguments += '--open' }
Write-Host '工作台正在启动。请保留此窗口，按 Ctrl+C 停止服务。'
& $projectPython @launchArguments
exit $LASTEXITCODE
