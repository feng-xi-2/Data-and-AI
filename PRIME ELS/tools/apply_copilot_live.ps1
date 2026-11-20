<#  Copilot AI instructions + measure descriptions in the open Power BI Desktop model (no data reload) - Windows PowerShell 5.1.
    Called by tools/copilot_ai.py:
      -Mode get -File out.json      writes { culture: <linguistic metadata JSON>, descriptions: {_KPI measure: text}, tooling: <PBI_ProTooling> }
      -Mode set -File payload.json  payload = { "culture": "<linguistic metadata JSON>", "descriptions": [ {table, name, description} ],
                                               "tooling": "CopilotTooling" }
    Prints what it changed and exits non-zero on any problem - never silent. #>
param([int]$ProcId, [ValidateSet("get", "set")][string]$Mode, [string]$File, [string]$Culture = "en-US")
$ErrorActionPreference = "Stop"
$amo = Join-Path $PSScriptRoot "amo"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path $amo $d) }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
if (-not $ms) { Write-Output "FAILED: no engine under PBIDesktop $ProcId"; exit 2 }
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$port")
try {
    $model = $srv.Databases[0].Model
    $cul = $model.Cultures.Find($Culture)
    if ($Mode -eq "get") {
        $txt = if ($cul -and $cul.LinguisticMetadata) { $cul.LinguisticMetadata.Content } else { "" }
        $desc = @{}; $t = $model.Tables.Find("_KPI")
        if ($t) { foreach ($m in $t.Measures) { if ($m.Description) { $desc[$m.Name] = $m.Description } } }
        $ann = $model.Annotations.Find("PBI_ProTooling")
        $visible = @{}
        foreach ($vt in $model.Tables | Where-Object { -not $_.IsHidden }) {
            $visible[$vt.Name] = @(@($vt.Columns | Where-Object { -not $_.IsHidden -and $_.Type -ne "RowNumber" } | ForEach-Object Name) + @($vt.Measures | Where-Object { -not $_.IsHidden } | ForEach-Object Name))
        }
        $states = @{}; foreach ($vt in $model.Tables) { if ($vt.Partitions.Count -and $vt.Partitions[0].SourceType -eq "Calculated") { $states[$vt.Name] = "$($vt.Partitions[0].State)" } }
        $out = @{ culture = $txt; descriptions = $desc; tooling = $(if ($ann) { $ann.Value } else { "" }); visible = $visible; calculated = $states } | ConvertTo-Json -Depth 4 -Compress
        [IO.File]::WriteAllText($File, $out, (New-Object Text.UTF8Encoding($false)))
        Write-Output "read culture ${Culture}: $($txt.Length) characters of linguistic metadata, $($desc.Count) _KPI measure descriptions"
        exit 0
    }
    $p = [IO.File]::ReadAllText($File, [Text.Encoding]::UTF8) | ConvertFrom-Json
    if (-not $cul) {
        $cul = New-Object Microsoft.AnalysisServices.Tabular.Culture; $cul.Name = $Culture; $model.Cultures.Add($cul)
        Write-Output "created culture $Culture"
    }
    if (-not $cul.LinguisticMetadata) {
        $lm = New-Object Microsoft.AnalysisServices.Tabular.LinguisticMetadata
        $lm.ContentType = [Microsoft.AnalysisServices.Tabular.ContentType]::Json
        $cul.LinguisticMetadata = $lm
    }
    $cul.LinguisticMetadata.Content = $p.culture
    $n = 0; $miss = @()
    foreach ($d in $p.descriptions) {
        $t = $model.Tables.Find($d.table); $m = if ($t) { $t.Measures.Find($d.name) } else { $null }
        if (-not $m) { $miss += "$($d.table)[$($d.name)]"; continue }
        if ($m.Description -ne $d.description) { $m.Description = $d.description; $n++ }
    }
    $ann = $model.Annotations.Find("PBI_ProTooling")
    if (-not $ann) { $ann = New-Object Microsoft.AnalysisServices.Tabular.Annotation; $ann.Name = "PBI_ProTooling"; $ann.Value = "[]"; $model.Annotations.Add($ann) }
    if ($ann.Value -notmatch [regex]::Escape($p.tooling)) {
        $lst = @($ann.Value | ConvertFrom-Json) + $p.tooling | Where-Object { $_ }
        $ann.Value = "[" + (($lst | ForEach-Object { '"' + $_ + '"' }) -join ",") + "]"
    }
    $model.SaveChanges() | Out-Null
    Write-Output "saved: AI instructions in culture $Culture, $n measure description(s) changed, PBI_ProTooling = $($ann.Value)"
    if ($miss.Count) { Write-Output "FAILED: measures not found: $($miss -join ', ')"; exit 1 }

    # Copilot answer tables (calculated): drop retired names, create / update the expression, recalculate them, then column descriptions
    foreach ($rn in @($p.retire)) { $old = $model.Tables.Find($rn); if ($old) { [void]$model.Tables.Remove($old); Write-Output "removed retired table '$rn'" } }
    foreach ($at in $p.tables) {
        $t = $model.Tables.Find($at.name)
        if (-not $t) {
            $t = New-Object Microsoft.AnalysisServices.Tabular.Table; $t.Name = $at.name
            $src = New-Object Microsoft.AnalysisServices.Tabular.CalculatedPartitionSource; $src.Expression = $at.expression
            $part = New-Object Microsoft.AnalysisServices.Tabular.Partition; $part.Name = $at.name; $part.Source = $src
            $t.Partitions.Add($part); $model.Tables.Add($t)
            Write-Output "created table '$($at.name)'"
        } elseif ($t.Partitions[0].Source.Expression -ne $at.expression) {
            $t.Partitions[0].Source.Expression = $at.expression
            Write-Output "updated table '$($at.name)'"
        }
        $t.Description = $at.description
        $t.RequestRefresh([Microsoft.AnalysisServices.Tabular.RefreshType]::Full)
    }
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $model.SaveChanges() | Out-Null
    Write-Output ("recalculated the answer tables in {0:N0} s" -f $sw.Elapsed.TotalSeconds)
    foreach ($at in $p.tables) {
        $t = $model.Tables.Find($at.name)
        foreach ($c in $t.Columns) {
            if ($c.Type -eq [Microsoft.AnalysisServices.Tabular.ColumnType]::RowNumber) { continue }
            $spec = $at.columns.PSObject.Properties[$c.Name]
            if ($spec) { $c.Description = $spec.Value.description; if ($spec.Value.format) { $c.FormatString = $spec.Value.format } }
            else { Write-Output "  column '$($at.name)'[$($c.Name)] has no description in copilot_ai.py" }
        }
        $state = $t.Partitions[0].State
        if ($state -ne "Ready") { Write-Output "FAILED: table '$($at.name)' is $state - $($t.Partitions[0].ErrorMessage)"; exit 1 }
    }

    # what Copilot sees: only config/copilot_fields.csv (everything else hidden - visuals keep working with hidden fields)
    $vis = $p.visible; $shown = 0; $hid = 0
    foreach ($t in $model.Tables) {
        $allow = $vis.PSObject.Properties[$t.Name]
        if (-not $allow) { if (-not $t.IsHidden) { $t.IsHidden = $true; $hid++ }; continue }
        $f = @($allow.Value); $all = $f -contains "*"
        $t.IsHidden = $false
        foreach ($c in $t.Columns) {
            if ($c.Type -eq [Microsoft.AnalysisServices.Tabular.ColumnType]::RowNumber) { continue }
            $want = -not ($all -or $f -contains $c.Name); if ($c.IsHidden -ne $want) { $c.IsHidden = $want }; if (-not $want) { $shown++ }
        }
        foreach ($m in $t.Measures) {
            $want = -not ($all -or $f -contains $m.Name); if ($m.IsHidden -ne $want) { $m.IsHidden = $want }; if (-not $want) { $shown++ }
        }
        $missing = @($f | Where-Object { $_ -ne "*" -and -not $t.Columns.Find($_) -and -not $t.Measures.Find($_) })
        if ($missing.Count) { Write-Output "FAILED: config/copilot_fields.csv names unknown fields of '$($t.Name)': $($missing -join ', ')"; exit 1 }
    }
    $model.SaveChanges() | Out-Null
    Write-Output "Copilot sees $shown fields in $(@($model.Tables | Where-Object { -not $_.IsHidden }).Count) tables; $hid table(s) newly hidden"
} finally { $srv.Disconnect() }
