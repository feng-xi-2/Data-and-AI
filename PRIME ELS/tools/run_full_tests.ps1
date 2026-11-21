<#  Full test chain on the all-sites model with heartbeat: open -> refresh -> field audit -> site-by-site replay -> filter-by-filter replay.
    The scheduled refresh is paused during the run and resumed at the end (also on failure).
    -SkipOpen       : use the Desktop model that is already open and refreshed (tests only).
    -Sites A,B      : only these sites (SiteCode list) in every test step.
    -KeepTaskPaused : leave the scheduled refresh paused at the end (e.g. while Desktop cannot refresh: sign-in pending). #>
param([switch]$SkipOpen, [switch]$KeepTaskPaused, [string]$Sites = "")
$ErrorActionPreference = "Continue"
$sa = if ($Sites) { @("--sites", $Sites) } else { @() }
$T = $PSScriptRoot
$env:PYTHONIOENCODING = "utf-8"
function Say($m) { Write-Output ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m) }
$task = "PRIME ELS Hypercare refresh"
try {
    Disable-ScheduledTask -TaskName $task | Out-Null; Say "scheduled refresh paused"
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'refresh_desktop\.ps1' })) { break }
        Say "heartbeat: waiting for a running refresh to finish"; Start-Sleep 30
    }
    if (-not $SkipOpen) {
    & py -u (Join-Path $T "open_model.py") (Join-Path (Split-Path $T) "dist\ALL_SITES\WH Hypercare KPI.pbip") --timeout 900
    if ($LASTEXITCODE -ne 0) { Say "FAILED: model did not open"; exit 1 }
    }
    $pd = (Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1).Id
    if (-not $pd) { Say "FAILED: no Power BI Desktop open"; exit 1 }
    if (-not $SkipOpen) {
    Start-Sleep 15
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $T "with_heartbeat.ps1") -Label "full refresh" -Exe powershell.exe `
        -ArgLine "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $T 'refresh_desktop.ps1')`" -Tables * -MaxParallel 3 -Retries 3"
    }
    Say "=== 1/5 FIELD BY FIELD"
    & py -u (Join-Path $T "audit_fields.py") $pd @sa
    Say "=== 2/5 SITE BY SITE (every visual, default + last 4 days)"
    & py -u (Join-Path $T "visual_replay.py") $pd --days 4 @sa
    Say "=== 3/5 FILTER BY FILTER (every slicer, 2 values per site)"
    & py -u (Join-Path $T "visual_replay.py") $pd --filters 2 @sa
    Say "=== 4/5 KPI RECONCILIATION (model vs independent replica SQL, every site, last 3 shift days)"
    & py -u (Join-Path $T "reconcile_kpis.py") $pd --days 3 @sa
    if ($LASTEXITCODE -ne 0) { Say "FAILED: reconciliation did not complete" }
    Say "=== 5/5 REPORT INTENT (catalogue + day / site / snapshot checks on the site-by-site replay)"
    & py -u (Join-Path $T "report_intent.py") $pd
    Say "ALL TESTS DONE"
}
finally {
    if ($KeepTaskPaused) { Say "scheduled refresh left PAUSED (-KeepTaskPaused) - enable with: Enable-ScheduledTask -TaskName '$task'" }
    else { Enable-ScheduledTask -TaskName $task | Out-Null; Say "scheduled refresh resumed" }
}


