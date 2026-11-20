<#  Trace where refresh time goes (Analysis Services ProgressReportEnd events) for one or more partitions of one site,
    refreshed in ONE transaction like the scheduled refresh. Windows PowerShell 5.1.
    powershell -File trace_partition.ps1 -Tables "Data Health|TTAT" -Site BINHDUONG [-MaxParallel 3] [-Detail]
    Output: wall clock, total ms per event type (ExecuteSql = Power Query + replica, TabularSequencePoint = recalculation
    of dependent calculated objects, Commit...), ExecuteSql per partition, biggest reads. #>
param([string]$Tables = "Data Health", [string]$Site = "BINHDUONG", [int]$MaxParallel = 3, [switch]$Detail)
$ErrorActionPreference = "Stop"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll", "Microsoft.AnalysisServices.dll") {
    Add-Type -Path (Join-Path $PSScriptRoot "amo\$d")
}
$p = Get-Process PBIDesktop | Select-Object -First 1
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server
$srv.Connect("Data Source=localhost:$port")
$db = $srv.Databases[0]
$tr = $srv.Traces.Add("prof_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$ev = $tr.Events.Add([Microsoft.AnalysisServices.TraceEventClass]::ProgressReportEnd)
foreach ($c in "EventSubclass", "Duration", "ObjectName", "ObjectPath", "TextData", "StartTime", "EndTime", "IntegerData") {
    [void]$ev.Columns.Add([Microsoft.AnalysisServices.TraceColumn]::$c)
}
$tr.Update()
$events = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
$h = Register-ObjectEvent -InputObject $tr -EventName OnEvent -MessageData $events -Action {
    $t = "$($EventArgs.TextData)"
    [void]$Event.MessageData.Add([pscustomobject]@{ Sub = "$($EventArgs.EventSubclass)"; Ms = $EventArgs.Duration; Obj = $EventArgs.ObjectName;
        Txt = $t.Substring(0, [Math]::Min(120, $t.Length)); Rows = $EventArgs.IntegerData; Start = $EventArgs.StartTime })
}
$tr.Start()
$names = @($Tables.Split("|") | Where-Object { $_ })
$missing = @($names | Where-Object { -not $db.Model.Tables.Contains($_) -or -not $db.Model.Tables[$_].Partitions.Contains("$_ - $Site") })
if ($missing.Count) { Write-Output "WARNING: no partition '<table> - $Site' for: $($missing -join ', ')" }
$objs = @($names | Where-Object { $missing -notcontains $_ } | ForEach-Object { @{ database = $db.Name; table = $_; partition = "$_ - $Site" } })
$tmsl = @{ sequence = @{ maxParallelism = $MaxParallel; operations = @(@{ refresh = @{ type = "dataOnly"; objects = $objs } }) } } | ConvertTo-Json -Depth 8 -Compress
$t0 = Get-Date
$r = $srv.Execute($tmsl)
$wall = ((Get-Date) - $t0).TotalSeconds
Start-Sleep 3
$tr.Stop(); Unregister-Event -SourceIdentifier $h.Name; $tr.Drop()
$errs = @($r | ForEach-Object { $_.Messages } | Where-Object { $_ -is [Microsoft.AnalysisServices.XmlaError] } | ForEach-Object { $_.Description })
"wall clock {0:N1}s for {1} partition(s) of {2}, maxParallel {3}; errors: {4}" -f $wall, $objs.Count, $Site, $MaxParallel, $(if ($errs.Count) { $errs -join " | " } else { "none" })
"-- total ms by event type"
$events | Group-Object Sub | Sort-Object { -($_.Group | Measure-Object Ms -Sum).Sum } | ForEach-Object { "  {0,-22} {1,8} ms  ({2} events)" -f $_.Name, ($_.Group | Measure-Object Ms -Sum).Sum, $_.Count }
"-- ExecuteSql (Power Query + replica) per partition"
$events | Where-Object { $_.Sub -eq "ExecuteSql" } | Sort-Object Ms -Descending | ForEach-Object { "  {0,8} ms  {1}" -f $_.Ms, $_.Obj }
"-- ReadData"
$events | Where-Object { $_.Sub -eq "ReadData" } | Sort-Object Ms -Descending | Select-Object -First 8 | ForEach-Object { "  {0,8} ms {1,9} rows  {2}" -f $_.Ms, $_.Rows, $_.Obj }
"-- slowest other events"
$events | Where-Object { $_.Sub -notin "ExecuteSql", "ReadData" } | Sort-Object Ms -Descending | Select-Object -First 8 | ForEach-Object { "  {0,8} ms  {1,-22} {2}" -f $_.Ms, $_.Sub, $_.Txt }
if ($Detail) { $events | Sort-Object Start | Select-Object Sub, Ms, Rows, Obj, Txt | Format-Table -AutoSize | Out-String -Width 220 }
$srv.Disconnect()
