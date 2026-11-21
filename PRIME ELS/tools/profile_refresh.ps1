<#  Refresh-time profile of the open WH Hypercare KPI model: every partition of one site refreshed alone, then one calculate pass.
    powershell -File profile_refresh.ps1 -Site BINHDUONG [-Tables "TTAT|User Activity"] [-OutCsv ..\docs\_refresh_profile_BINHDUONG.csv]
    Prints a heartbeat at least every 30 s (also while one partition is still running) and every error. Windows PowerShell 5.1. #>
param([string]$Site = "BINHDUONG", [string]$Tables = "*", [string]$OutCsv = "", [int]$HeartbeatSec = 30)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Output ("[{0}] {1}" -f (Get-Date -Format HH:mm:ss), $m); [Console]::Out.Flush() }
$t0 = Get-Date
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") {
    Add-Type -Path (Join-Path $PSScriptRoot "amo\$d")
}
$tAmo = ((Get-Date) - $t0).TotalSeconds
$p = Get-Process PBIDesktop -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Say "FAILED: no Power BI Desktop open"; exit 1 }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$tFind = ((Get-Date) - $t0).TotalSeconds - $tAmo
$t1 = Get-Date
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server
$srv.Connect("Data Source=localhost:$port")
$db = $srv.Databases[0]
$parts = @()
foreach ($t in $db.Model.Tables) {
    if ($Tables -ne "*" -and ($Tables.Split("|") -notcontains $t.Name)) { continue }
    foreach ($pt in $t.Partitions) {
        if ($pt.SourceType -ne "M") { continue }
        $s = if ($pt.Name -like "$($t.Name) - *") { $pt.Name.Substring($t.Name.Length + 3) } else { "(config)" }
        if ($s -eq $Site) { $parts += ,@($t.Name, $pt.Name) }
    }
}
$tMeta = ((Get-Date) - $t1).TotalSeconds
Say ("startup: AMO load {0:N1}s, find engine {1:N1}s, connect+metadata {2:N1}s; {3} partitions for {4}" -f $tAmo, $tFind, $tMeta, $parts.Count, $Site)

$rs = [runspacefactory]::CreateRunspace(); $rs.Open()
$job = { param($srv, $tmsl) $r = $srv.Execute($tmsl); @($r | ForEach-Object { $_.Messages } | Where-Object { $_ -is [Microsoft.AnalysisServices.XmlaError] } | ForEach-Object { $_.Description }) }
function Run-Tmsl($tmsl, $label) {
    $ps = [powershell]::Create(); $ps.Runspace = $rs
    [void]$ps.AddScript($job).AddArgument($srv).AddArgument($tmsl)
    $st = Get-Date; $beat = Get-Date; $h = $ps.BeginInvoke()
    while (-not $h.AsyncWaitHandle.WaitOne(1000)) {
        if (((Get-Date) - $beat).TotalSeconds -ge $HeartbeatSec) { Say "heartbeat: $label running $([int]((Get-Date) - $st).TotalSeconds)s"; $beat = Get-Date }
    }
    $errs = @($ps.EndInvoke($h)); $ps.Dispose()
    return @{ secs = ((Get-Date) - $st).TotalSeconds; err = ($errs -join " | ") }
}
$rows = @()
foreach ($x in $parts) {
    $tmsl = @{ refresh = @{ type = "dataOnly"; objects = @(@{ database = $db.Name; table = $x[0]; partition = $x[1] }) } } | ConvertTo-Json -Depth 6 -Compress
    $r = Run-Tmsl $tmsl $x[0]
    Say ("{0,-42} {1,7:N1}s {2}" -f $x[0], $r.secs, $(if ($r.err) { "ERROR " + $r.err.Substring(0, [Math]::Min(160, $r.err.Length)) } else { "" }))
    $rows += [pscustomobject]@{ Site = $Site; Table = $x[0]; Seconds = [math]::Round($r.secs, 1); Error = $r.err }
}
$c = Run-Tmsl ((@{ refresh = @{ type = "calculate"; objects = @(@{ database = $db.Name }) } } | ConvertTo-Json -Depth 6 -Compress)) "calculate"
Say ("calculate pass (whole model) {0:N1}s {1}" -f $c.secs, $c.err)
$rows += [pscustomobject]@{ Site = $Site; Table = "(calculate pass)"; Seconds = [math]::Round($c.secs, 1); Error = $c.err }
$rows += [pscustomobject]@{ Site = $Site; Table = "(startup: AMO+engine+metadata)"; Seconds = [math]::Round($tAmo + $tFind + $tMeta, 1); Error = "" }
$rs.Close(); $srv.Disconnect()
if ($OutCsv) { $rows | Export-Csv $OutCsv -NoTypeInformation -Encoding UTF8 }
Say ("done: sum of partitions {0:N0}s, calculate {1:N0}s, total {2:N0}s" -f (($rows | Where-Object { $_.Table -notlike "(*" } | Measure-Object Seconds -Sum).Sum), $c.secs, ((Get-Date) - $t0).TotalSeconds)
