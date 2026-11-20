<#  Push measure expressions into the open Power BI Desktop model (no data reload) - Windows PowerShell 5.1.
    powershell -File apply_measures.ps1 -ProcId <PBIDesktop PID> -Json measures.json
    measures.json = [ { "tableName": "...", "name": "...", "expression": "..." }, ... ]
    Prints one line per measure (UPDATED / NOT FOUND) and the engine's error state after the save - never silent. #>
param([int]$ProcId, [string]$Json)
$amo = Join-Path $PSScriptRoot "amo"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path $amo $d) }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
if (-not $ms) { Write-Output "FAILED: no engine under PBIDesktop $ProcId"; exit 2 }
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$port")
$model = $srv.Databases[0].Model
$items = @((Get-Content $Json -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_ })
$n = 0
foreach ($it in $items) {
    $t = $model.Tables[$it.tableName]
    $m = if ($t) { $t.Measures[$it.name] } else { $null }
    if (-not $m) { Write-Output "NOT FOUND: $($it.tableName)[$($it.name)]"; continue }
    $m.Expression = $it.expression; $n++
    Write-Output "UPDATED: $($it.name)"
}
$model.SaveChanges() | Out-Null
$bad = @($model.Tables | ForEach-Object { $_.Measures } | Where-Object { $_.State -ne "Ready" } | ForEach-Object { "$($_.Name): $($_.ErrorMessage)" })
if ($bad.Count) { Write-Output "FAILED: $($bad.Count) measure(s) in error after save:"; $bad | Select-Object -First 10 | ForEach-Object { Write-Output "  $_" }; $srv.Disconnect(); exit 1 }
Write-Output "saved $n measure(s); all measures Ready"
$srv.Disconnect()
