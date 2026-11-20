<#  Self-check: evaluate every measure of the open WH Hypercare KPI model for every configured site (Site slicer = that site).
    Writes tools/_selfcheck_measures.csv (site, measure, value / ERROR text). Windows PowerShell 5.1. #>
param([int]$TimeoutSec = 120, [int]$ProcId = 0, [string]$OutCsv = "")
$bin = (Get-Process PBIDesktop | Select-Object -First 1).Path | Split-Path
Add-Type -Path (Join-Path $bin "Microsoft.PowerBI.AdomdClient.dll")
if ($ProcId) { $p = Get-Process -Id $ProcId } else { $p = Get-Process PBIDesktop | Where-Object { $_.MainWindowTitle -like "WH Hypercare KPI*" } | Select-Object -First 1 }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $cn.Open()
function Q($dax) { $c = $cn.CreateCommand(); $c.CommandText = $dax; $c.CommandTimeout = $TimeoutSec; $r = $c.ExecuteReader(); $rows = @(); while ($r.Read()) { $row = @(); for ($i = 0; $i -lt $r.FieldCount; $i++) { $row += $r.GetValue($i) }; $rows += ,$row }; $r.Close(); return ,$rows }
$measures = foreach ($r in (Q 'EVALUATE SELECTCOLUMNS(INFO.MEASURES(), "N", [Name])')) { $r[0] }
$sites = foreach ($r in (Q 'EVALUATE VALUES(Cfg_Site[SiteCode])')) { $r[0] }
$out = foreach ($s in $sites) {
  foreach ($m in $measures) {
    $esc = $m.Replace("]", "]]")
    $t0 = Get-Date
    try { $res = Q "EVALUATE ROW(""v"", CALCULATE([$esc], Cfg_Site[SiteCode] = ""$s""))"; $v = $res[0][0]; $st = "OK" }
    catch { $v = ($_.Exception.InnerException, $_.Exception | Where-Object { $_ } | Select-Object -First 1).Message; $st = "ERROR" }
    [pscustomobject]@{ Site = $s; Measure = $m; Status = $st; Value = "$v"; Ms = [int]((Get-Date) - $t0).TotalMilliseconds }
  }
}
$cn.Close()
if (-not $OutCsv) { $OutCsv = Join-Path $PSScriptRoot "_selfcheck_measures.csv" }; $out | Export-Csv $OutCsv -NoTypeInformation -Encoding UTF8
"measures=$($measures.Count) sites=$($sites.Count) evaluated=$($out.Count) errors=$(@($out | Where-Object Status -eq 'ERROR').Count) slow(>10s)=$(@($out | Where-Object Ms -gt 10000).Count)"
$out | Where-Object Status -eq 'ERROR' | Group-Object Measure | ForEach-Object { "ERR $($_.Name) [$(($_.Group.Site) -join ',')]: $($_.Group[0].Value.Substring(0, [Math]::Min(200, $_.Group[0].Value.Length)))" }



