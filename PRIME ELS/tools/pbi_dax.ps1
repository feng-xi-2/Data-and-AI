<#  Run one DAX query against an open Power BI Desktop model and print the rows as JSON (Windows PowerShell 5.1).
    powershell -File pbi_dax.ps1 -ProcId <PBIDesktop PID> -Dax "EVALUATE ..." #>
param([int]$ProcId, [string]$Dax, [int]$TimeoutSec = 300)
$p = Get-Process -Id $ProcId
Add-Type -Path (Join-Path (Split-Path $p.Path) "Microsoft.PowerBI.AdomdClient.dll")
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
if (-not $ms) { '{"error":"no engine"}'; exit 0 }
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$cn = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $cn.Open()
try {
  $c = $cn.CreateCommand(); $c.CommandText = $Dax; $c.CommandTimeout = $TimeoutSec; $r = $c.ExecuteReader()
  $rows = New-Object System.Collections.ArrayList
  while ($r.Read()) { $o = [ordered]@{}; for ($i = 0; $i -lt $r.FieldCount; $i++) { $o[$r.GetName($i)] = $r.GetValue($i) }; [void]$rows.Add($o) }
  $r.Close(); ConvertTo-Json -InputObject @($rows) -Depth 3 -Compress
} catch { (@{ error = $_.Exception.Message } | ConvertTo-Json -Compress) } finally { $cn.Close() }
