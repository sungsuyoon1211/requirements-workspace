param([string]$InstallDir='', [string]$DataPath='', [switch]$NoLaunch, [switch]$NoShortcut)
$ErrorActionPreference = 'Stop'
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'RequirementsWorkspace' }
$InstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$configPath = Join-Path $InstallDir 'local-settings.json'
if (Test-Path -LiteralPath $configPath) {
    $existing = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $DataPath) { $DataPath = $existing.dataPath }
}
if (-not $DataPath) {
    Add-Type -AssemblyName System.Windows.Forms
    $choice = [System.Windows.Forms.MessageBox]::Show('팀 공용 작업폴더를 연결할까요? 예: 팀 전체가 사용하는 같은 폴더 선택 / 아니요: 이 PC에서 개인용으로 시작', '요건작업실 설치', 'YesNoCancel', 'Question')
    if ($choice -eq 'Cancel') { return }
    if ($choice -eq 'Yes') {
        $picker = New-Object System.Windows.Forms.FolderBrowserDialog
        $picker.Description = '팀원 모두 같은 전용 작업폴더를 선택하세요. 계정·자료·요건이 함께 저장됩니다. 다른 문서 폴더와 구분하세요.'
        if ($picker.ShowDialog() -ne 'OK') { return }
        $DataPath = $picker.SelectedPath
    } else { $DataPath = Join-Path $InstallDir 'team-data' }
}
if (-not [System.IO.Path]::IsPathRooted($DataPath) -or $DataPath.Contains('"')) { throw '올바른 절대 폴더 경로가 필요합니다.' }
New-Item -ItemType Directory -Path $DataPath -Force | Out-Null
$probe = Join-Path $DataPath ('.install-probe-' + [Guid]::NewGuid().ToString('N'))
[System.IO.File]::WriteAllText($probe,'test')
Remove-Item -LiteralPath $probe
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
$stateFile = Join-Path $InstallDir 'running.json'
if (Test-Path -LiteralPath $stateFile) {
    $state = Get-Content -LiteralPath $stateFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $owned = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$state.processId)
    $expectedServer = Join-Path $InstallDir 'app/server.py'
    if ($owned -and $owned.CommandLine.Contains($expectedServer) -and $owned.CommandLine.Contains([string]$state.instance)) {
        Stop-Process -Id ([int]$state.processId)
    }
}
# Install only application/runtime files. Existing accounts and data are never overwritten.
foreach ($name in @('app','runtime')) {
    $destination = Join-Path $InstallDir $name
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Copy-Item -Path (Join-Path $PSScriptRoot ($name + '/*')) -Destination $destination -Recurse -Force
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'launch-local.ps1') -Destination $InstallDir -Force
@{dataPath=[System.IO.Path]::GetFullPath($DataPath)} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
if (-not $NoShortcut) {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($location in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))) {
        $shortcut = $shell.CreateShortcut((Join-Path $location '요건작업실.lnk'))
        $shortcut.TargetPath = (Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe')
        $shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $InstallDir 'launch-local.ps1') + '"'
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = '설치된 AI와 함께 요구사항을 작성합니다.'
        $shortcut.Save()
    }
}
Write-Output ('설치 완료: ' + $InstallDir)
if (-not $NoLaunch) { & (Join-Path $InstallDir 'launch-local.ps1') }
