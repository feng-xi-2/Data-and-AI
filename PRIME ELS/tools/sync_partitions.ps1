<#  Copy the Power Query (M) source of the given tables from the built TMDL into the open Desktop model - Windows PowerShell 5.1.
    Used after a config change (config/*.csv -> Cfg_* tables) so the open model gets it without reopening.
    powershell -File sync_partitions.ps1 -ProcId <PBIDesktop PID> -Json partitions.json
    partitions.json = [ { "table": "Cfg_Site", "expression": "<M>" }, ... ]                                  (single-partition tables)
                    | [ { "table": "Inventory", "partition": "Inventory - JAKARTA", "expression": "<M>" }, ... ]  (per-site partitions)
    Normally called by sync_partitions.py (builds the M from sql/ + config/ and keeps dist/ALL_SITES in step). #>
param([int]$ProcId, [string]$Json)
$amo = Join-Path $PSScriptRoot "amo"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path $amo $d) }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
if (-not $ms) { Write-Output "FAILED: no engine under PBIDesktop $ProcId"; exit 2 }
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$port")
$model = $srv.Databases[0].Model
if (-not (Test-Path $Json)) { Write-Output "FAILED: input file not found: $Json"; $srv.Disconnect(); exit 3 }
$items = @((Get-Content $Json -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_ })
foreach ($it in $items) {
    $t = $model.Tables[$it.table]
    if (-not $t) { Write-Output "FAILED: table $($it.table) not found"; $srv.Disconnect(); exit 1 }
    if ($it.partition) {
        $p = $t.Partitions[$it.partition]
        if (-not $p) { Write-Output "FAILED: partition '$($it.partition)' not found in $($it.table)"; $srv.Disconnect(); exit 1 }
    } elseif ($t.Partitions.Count -eq 1) { $p = $t.Partitions[0] }
    else { Write-Output "FAILED: $($it.table) has $($t.Partitions.Count) partitions - name the partition"; $srv.Disconnect(); exit 1 }
    if ($p.Source.Expression -eq $it.expression) { Write-Output "unchanged: $($p.Name)"; continue }
    $p.Source.Expression = $it.expression
    Write-Output "UPDATED source: $($p.Name)"
}
$model.SaveChanges() | Out-Null
Write-Output "saved"
$srv.Disconnect()

