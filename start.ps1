param(
    [string]$BindAddress = '127.0.0.1',
    [int]$Port = 8765,
    [string]$DataPath = '',
    [switch]$SecureCookie
)
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
if (-not (Test-Path -LiteralPath $runtime)) {
    $runtime = (Get-Command python -ErrorAction Stop).Source
}
$serverArgs = @((Join-Path $PSScriptRoot 'server.py'), '--host', $BindAddress, '--port', "$Port")
if ($DataPath) { $serverArgs += @('--data', $DataPath) }
if ($SecureCookie) { $serverArgs += '--secure-cookie' }
& $runtime @serverArgs
