<#  Proves visuals stay usable during a refresh: runs a refresh cycle (refresh_desktop.ps1) and meanwhile queries the model
    every second like a visual does. Any query error (e.g. "needs to be recalculated" / "Error fetching data") is reported.
    powershell -File watch_refresh.ps1 [-Tables "<HOT tables>"] [-Sites BINHDUONG]   Windows PowerShell 5.1 #>
param([string]$Tables = "", [string]$Sites = "*")
$ErrorActionPreference = "Stop"
$T = $PSScriptRoot
if (-not $Tables) { $Tables = (Import-Csv (Join-Path (Split-Path $T) "config\refresh_policy.csv") | Where-Object Tier -eq HOT).Tables }
$p = Get-Process PBIDesktop | Select-Object -First 1
Add-Type -Path (Join-Path (Split-Path $p.Path) "Microsoft.PowerBI.AdomdClient.dll")
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$job = Start-Job -ScriptBlock { param($s, $t, $si) & powershell -NoProfile -ExecutionPolicy Bypass -File $s -Tables $t -Sites $si 2>&1 } `
    -ArgumentList (Join-Path $T "refresh_desktop.ps1"), $Tables, $Sites
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $cn.Open()
$dax = 'EVALUATE ROW("pph", [KPI PPH], "ttat", [KPI TTAT In], "util", [KPI Loc Util], "users", [KPI Active Users], "rows", COUNTROWS(TTAT))'
$ok = 0; $bad = 0; $errs = @{}; $t0 = Get-Date; $beat = Get-Date
while ($job.State -eq "Running") {
    try { $c = $cn.CreateCommand(); $c.CommandText = $dax; $c.CommandTimeout = 60; $r = $c.ExecuteReader(); while ($r.Read()) {}; $r.Close(); $ok++ }
    catch { $bad++; $m = $_.Exception.Message; $m = $m.Substring(0, [Math]::Min(140, $m.Length)); $errs[$m] = 1 + [int]$errs[$m] }
    if (((Get-Date) - $beat).TotalSeconds -ge 30) { Write-Output ("[{0}] heartbeat: refresh running {1}s, visual queries ok {2}, failed {3}" -f (Get-Date -Format HH:mm:ss), [int]((Get-Date) - $t0).TotalSeconds, $ok, $bad); $beat = Get-Date }
    Start-Sleep -Milliseconds 1000
}
Receive-Job $job | Select-Object -Last 3
$cn.Close()
Write-Output ("RESULT: during the refresh {0} visual queries succeeded, {1} failed" -f $ok, $bad)
$errs.Keys | ForEach-Object { Write-Output ("  {0}x {1}" -f $errs[$_], $_) }
if ($bad) { exit 1 }
