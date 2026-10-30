param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$settings = Join-Path $root 'local-settings.json'
if (-not (Test-Path -LiteralPath $settings)) { throw '설치.cmd를 먼저 실행하세요.' }
$config = Get-Content -LiteralPath $settings -Raw -Encoding UTF8 | ConvertFrom-Json
$state = Join-Path $root 'running.json'
if (Test-Path -LiteralPath $state) {
    $previous = Get-Content -LiteralPath $state -Raw -Encoding UTF8 | ConvertFrom-Json
    try {
        $check = Invoke-RestMethod -Uri ($previous.url + '/api/bootstrap') -TimeoutSec 2
        if ($check.instance -eq $previous.instance) {
            if (-not $NoBrowser) { Start-Process $previous.url }
            return
        }
    } catch {}
}
$port = $null
foreach ($candidate in 8765..8795) {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $candidate)
    try { $listener.Start(); $port = $candidate; break } catch {} finally { $listener.Stop() }
}
if ($null -eq $port) { throw '사용 가능한 로컬 포트가 없습니다.' }
$instance = [Guid]::NewGuid().ToString('N')
$runtime = Join-Path $root 'runtime/python.exe'
$server = Join-Path $root 'app/server.py'
$aiData = Join-Path $root 'ai-local'
$logs = Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logs -Force | Out-Null
# Each argument is quoted independently; no command string is sent to another shell.
$arguments = '"{0}" --host 127.0.0.1 --port {1} --data "{2}" --ai-data "{3}" --instance-id {4}' -f $server,$port,$config.dataPath,$aiData,$instance
$process = Start-Process -FilePath $runtime -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'server.out.log') -RedirectStandardError (Join-Path $logs 'server.err.log')
$url = 'http://127.0.0.1:' + $port
for ($attempt=0; $attempt -lt 40; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $check = Invoke-RestMethod -Uri ($url + '/api/bootstrap') -TimeoutSec 2
        if ($check.instance -eq $instance) {
            @{url=$url; instance=$instance; processId=$process.Id} | ConvertTo-Json | Set-Content -LiteralPath $state -Encoding UTF8
            if (-not $NoBrowser) { Start-Process $url }
            Write-Output $url
            return
        }
    } catch {}
    if ($process.HasExited) { break }
}
throw ('실행하지 못했습니다. 공유폴더 연결과 로그를 확인하세요: ' + $logs)
