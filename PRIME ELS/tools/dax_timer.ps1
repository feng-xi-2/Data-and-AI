<#  Time DAX queries on an open Power BI Desktop model, cold cache (cache cleared before every query) - finds slow measures.
    powershell -File dax_timer.ps1 -ProcId <PBIDesktop PID> -File <queries.txt>    (one query per line: label<TAB>DAX) #>
param([int]$ProcId, [string]$File, [int]$TimeoutSec = 120, [switch]$Warm)
$p = Get-Process -Id $ProcId
Add-Type -Path (Join-Path (Split-Path $p.Path) "Microsoft.PowerBI.AdomdClient.dll")
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
if (-not $ms) { "FAILED: no engine for PID $ProcId"; exit 1 }
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $cn.Open()
$c = $cn.CreateCommand(); $c.CommandText = "SELECT [CATALOG_NAME] FROM `$SYSTEM.DBSCHEMA_CATALOGS"; $r = $c.ExecuteReader(); [void]$r.Read(); $db = $r.GetValue(0); $r.Close()
$clear = "<ClearCache xmlns=`"http://schemas.microsoft.com/analysisservices/2003/engine`"><Object><DatabaseID>$db</DatabaseID></Object></ClearCache>"
foreach ($line in Get-Content $File -Encoding UTF8) {
    if (-not $line.Trim() -or $line.StartsWith("#")) { continue }
    $label, $dax = $line.Split("`t", 2)
    if (-not $Warm) { $k = $cn.CreateCommand(); $k.CommandText = $clear; [void]$k.ExecuteNonQuery() }
    $t0 = Get-Date
    try {
        $q = $cn.CreateCommand(); $q.CommandText = $dax; $q.CommandTimeout = $TimeoutSec; $r = $q.ExecuteReader(); $n = 0
        while ($r.Read()) { $n++ }; $r.Close()
        "{0,7:N0} ms  {1,5} rows  {2}" -f ((Get-Date) - $t0).TotalMilliseconds, $n, $label
    } catch { "{0,7:N0} ms  ERROR  {1}: {2}" -f ((Get-Date) - $t0).TotalMilliseconds, $label, $_.Exception.Message.Split([Environment]::NewLine)[0] }
}
$cn.Close()
