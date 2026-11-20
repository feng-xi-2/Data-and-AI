<#  Close the open WH Hypercare KPI Desktop, reopen the given .pbip and run the per-site refresh - with a heartbeat at least every 30 s.
    powershell -File reopen_and_refresh.ps1 -Pbip "<path>.pbip" #>
param([string]$Pbip)
function Say($m) { Write-Output ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m) }
Get-Process PBIDesktop -ErrorAction SilentlyContinue | ForEach-Object {
    $id = $_.Id; Say "closing Desktop $id ($($_.MainWindowTitle))"
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}
Start-Sleep 3
Say "opening $Pbip"
Start-Process $Pbip
$ok = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep 15
    $p = Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1
    $ms = if ($p) { Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)" }
    Say "heartbeat: Desktop $($p.Id) '$($p.MainWindowTitle)' engine=$([bool]$ms)"
    if ($p -and $ms -and $p.MainWindowTitle -like "WH Hypercare KPI*") { $ok = $true; break }
}
if (-not $ok) { Say "FAILED: Desktop did not open the model within 10 min (sign-in prompt? check the screen)"; exit 2 }
Start-Sleep 20
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "with_heartbeat.ps1") -Label "full refresh" -Exe powershell.exe `
    -ArgLine "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $PSScriptRoot 'refresh_desktop.ps1')`" -Tables * -MaxParallel 3 -Retries 3"
exit $LASTEXITCODE
