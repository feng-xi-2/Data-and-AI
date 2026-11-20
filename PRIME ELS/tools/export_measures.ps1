param([string]$Def, [string]$Out)
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path $PSScriptRoot "amo\$d") }
$db = [Microsoft.AnalysisServices.Tabular.TmdlSerializer]::DeserializeDatabaseFromFolder($Def)
$list = foreach ($t in $db.Model.Tables) { foreach ($m in $t.Measures) { [ordered]@{ tableName = $t.Name; name = $m.Name; expression = $m.Expression } } }
ConvertTo-Json -InputObject @($list) -Depth 4 | Set-Content $Out -Encoding UTF8
"exported $(@($list).Count) measures"
