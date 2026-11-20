param([string]$Only = "")
$amo = Join-Path $PSScriptRoot "amo"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path $amo $d) }
$p = Get-Process PBIDesktop | Where-Object { $_.MainWindowTitle -like "WH Hypercare KPI*" } | Select-Object -First 1
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$port"); $db = $srv.Databases[0]
$tabs = $db.Model.Tables | Where-Object { $_.Partitions.Count -gt 0 -and ($Only -eq "" -or $_.Name -match $Only) }
foreach ($t in $tabs) {
  foreach ($pt in $t.Partitions) {
    if ($pt.SourceType -ne 'M') { continue }
    $tmsl = @{ refresh = @{ type = "full"; objects = @(@{ database = $db.Name; table = $t.Name; partition = $pt.Name }) } } | ConvertTo-Json -Depth 6 -Compress
    $t0 = Get-Date; $r = $srv.Execute($tmsl); $sec = [int]((Get-Date) - $t0).TotalSeconds
    $errs = @($r | ForEach-Object { $_.Messages } | Where-Object { $_ -is [Microsoft.AnalysisServices.XmlaError] } | ForEach-Object { $_.Description })
    if ($errs.Count) { "FAIL`t$($pt.Name)`t$sec s`t$(($errs -join ' | ').Substring(0, [Math]::Min(300, ($errs -join ' | ').Length)))" } else { "OK`t$($pt.Name)`t$sec s" }
  }
}
$srv.Disconnect()
