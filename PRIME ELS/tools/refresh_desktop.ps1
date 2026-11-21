<#
  Refresh tables of every open "WH Hypercare KPI - <SITE>" model in Power BI Desktop (local Analysis Services, XMLA/TMSL).
  Called by tools/auto_refresh.py; Windows PowerShell 5.1 (the AMO libraries shipped with Power BI Desktop are .NET Framework).

    powershell -NoProfile -ExecutionPolicy Bypass -File refresh_desktop.ps1 -Tables "TTAT|User Activity"   # '*' = full model
#>
param([string]$Tables = "*", [string]$TitleLike = "WH Hypercare KPI*", [int]$MaxParallel = 3, [int]$Retries = 3, [string]$Sites = "*", [string]$NowUtc = "",
      [switch]$PlanOnly, [int]$StallSec = 240, [int]$HeartbeatSec = 30, [string]$ExcludeTitle = "")
$ErrorActionPreference = "Stop"
$tScript = Get-Date
function Phase($m) { Write-Output ("[{0}] {1} (+{2:N1}s)" -f (Get-Date -Format HH:mm:ss), $m, ((Get-Date) - $tScript).TotalSeconds) }

# Watchdog around one site transaction: heartbeat every HeartbeatSec; a transaction with NO data-source activity (Power Query
# containers idle, no outbound connection, engine idle) for StallSec is a stall - seen 31-Oct when Desktop had no stored credential
# for a new replica server (Data source settings 'Type: Not Specified'): the engine waits for a sign-in that a scripted refresh can
# never show. The stall is reported with the fix and the cycle stops (never a silent hang).
function Invoke-Watched($srv, $tmsl, $site, $enginePid) {
    $ps = [powershell]::Create()
    [void]$ps.AddScript({ param($s, $t) $s.Execute($t) }).AddArgument($srv).AddArgument($tmsl)
    $h = $ps.BeginInvoke()
    $t0 = Get-Date; $lastAct = Get-Date; $lastBeat = Get-Date; $prev = @{}
    while (-not $h.IsCompleted) {
        Start-Sleep -Milliseconds 2000
        $procs = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$enginePid" | Where-Object { $_.Name -like "Microsoft.Mashup.Container*" } | ForEach-Object { [int]$_.ProcessId })
        $active = $false
        # activity = the Power Query containers working or connected; NOT the engine's CPU: Desktop keeps querying the engine for its own
        # visuals / metadata ('Working on it'), which hid a 14-min stall on 31-Oct (workstation locked -> token refresh needed sign-in)
        foreach ($pr in @(if ($procs.Count) { Get-Process -Id $procs -ErrorAction SilentlyContinue })) {
            $cpu = [double]$pr.CPU
            if ($prev.ContainsKey($pr.Id) -and ($cpu - $prev[$pr.Id]) -gt 0.05) { $active = $true }
            $prev[$pr.Id] = $cpu
        }
        # one connection table per loop (a call per container took ~1 s each and stretched the heartbeat)
        $remote = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue |
                    Where-Object { $procs -contains [int]$_.OwningProcess -and $_.RemoteAddress -notmatch '^(127\.|::1)' }).Count
        if ($active -or $remote -gt 0) { $lastAct = Get-Date }
        $idle = ((Get-Date) - $lastAct).TotalSeconds
        if (((Get-Date) - $lastBeat).TotalSeconds -ge $HeartbeatSec) {
            Write-Host ("[{0}] {1}: still refreshing ({2:N0}s, {3} source connection(s), idle {4:N0}s)" -f (Get-Date -Format HH:mm:ss), $site, ((Get-Date) - $t0).TotalSeconds, $remote, $idle)
            [Console]::Out.Flush(); $lastBeat = Get-Date
        }
        if ($idle -ge $StallSec) {
            $servers = @()
            $cfgPath = Join-Path (Split-Path $PSScriptRoot) "config\site_config.csv"
            if (Test-Path $cfgPath) { $servers = @(Import-Csv $cfgPath | Where-Object { $_.SiteCode -eq $site } | ForEach-Object { "$($_.ReplicaServer);$($_.ReplicaDatabase)"; if ($_.Databricks_Host) { $_.Databricks_Host } }) }
            if (Get-Process LogonUI -ErrorAction SilentlyContinue) {
                Write-Host (("[{0}] STALLED: {1} - no data-source activity for {2}s while the WORKSTATION IS LOCKED: the sign-in token for {3} needs an interactive refresh (Windows Hello / passwordless) that cannot show on a locked screen. " -f (Get-Date -Format HH:mm:ss), $site, $StallSec, ($servers -join " / ")) +
                    "Unlock (and sign in if Desktop asks); the next cycle refreshes. Unattended overnight refresh = the Power BI Service (gateway), see README.")
            } else {
            Write-Host (("[{0}] STALLED: {1} - no data-source activity for {2}s. Most likely Power BI Desktop has no stored credential for {3}. " -f (Get-Date -Format HH:mm:ss), $site, $StallSec, ($servers -join " / ")) +
                "Fix once in Desktop: Transform data > Data source settings > select the server > Edit Permissions > Credentials Edit... > Microsoft account > Sign in > Save; then rerun.")
            }
            try {   # cancel from a second connection (the first one is busy inside Execute)
                $c2 = New-Object Microsoft.AnalysisServices.Tabular.Server
                $c2.Connect($srv.ConnectionString)
                [void]$c2.Execute("<Cancel xmlns=`"http://schemas.microsoft.com/analysisservices/2003/engine`"><SessionID>$($srv.SessionID)</SessionID><CancelAssociated>true</CancelAssociated></Cancel>")
                $c2.Disconnect()
            } catch { Write-Host "   (cancel request failed: $($_.Exception.Message))" }
            return "STALLED"
        }
    }
    try { $r = $ps.EndInvoke($h) }
    catch { $m = if ($_.Exception.InnerException) { $_.Exception.InnerException.Message } else { $_.Exception.Message }; return "EXCEPTION: $m" }
    finally { $ps.Dispose() }
    return $r
}
# Microsoft AMO client (NuGet Microsoft.AnalysisServices.retail.amd64) - downloaded once into tools\amo (not shipped in the kit)
$amo = Join-Path $PSScriptRoot "amo"
if (-not (Test-Path (Join-Path $amo "Microsoft.AnalysisServices.Tabular.dll"))) {
    New-Item -ItemType Directory -Force $amo | Out-Null
    $pkg = Join-Path $env:TEMP "amo_retail.nupkg"
    Invoke-WebRequest "https://www.nuget.org/api/v2/package/Microsoft.AnalysisServices.retail.amd64" -OutFile $pkg -UseBasicParsing
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($pkg)
    $z.Entries | Where-Object { $_.FullName -match '^lib/net45/[^/]+\.dll$' } | ForEach-Object {
        [IO.Compression.ZipFileExtensions]::ExtractToFile($_, (Join-Path $amo $_.Name), $true) }
    $z.Dispose()
}
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") {
    Add-Type -Path (Join-Path $amo $d)
}

# one refresh at a time: two refreshes on the same Desktop model block each other and can crash Desktop
$lockFile = Join-Path $PSScriptRoot "refresh.lock"
try { $lockStream = [System.IO.File]::Open($lockFile, 'OpenOrCreate', 'ReadWrite', 'None') }
catch { Write-Output ("SKIPPED: another refresh is running (lock {0}) - this cycle does nothing" -f $lockFile); exit 3 }
$pbis = @(Get-Process PBIDesktop -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like $TitleLike -and (-not $ExcludeTitle -or $_.MainWindowTitle -ne $ExcludeTitle) })
if (-not $pbis) {   # title can be empty while a dialog has focus -> any Desktop that runs an engine
    $pbis = @(Get-Process PBIDesktop -ErrorAction SilentlyContinue | Where-Object { (-not $ExcludeTitle -or $_.MainWindowTitle -ne $ExcludeTitle) -and (Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($_.Id)") })
}
Phase "startup: AMO loaded, lock taken, $($pbis.Count) Desktop model(s) found"
if (-not $pbis) { Write-Output "FAILED: NO_OPEN_MODEL - open the .pbip in Power BI Desktop first"; exit 1 }
foreach ($p in $pbis) {
    $ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$($p.Id)"
    if (-not $ms) { Write-Output "$($p.MainWindowTitle): no engine yet"; continue }
    $port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
    $srv = New-Object Microsoft.AnalysisServices.Tabular.Server
    $srv.Connect("Data Source=localhost:$port")
    $db = $srv.Databases[0]
    Phase "connected to engine port $port"
    $want = if ($Tables -eq "*") { @($db.Model.Tables | ForEach-Object { $_.Name }) } else { @($Tables.Split("|")) }
    # incremental tables (config/incremental_policy.csv) have '<T> - <SITE>' (history) + '<T> - <SITE> - recent':
    # a scheduled cycle refreshes 'recent' only; history is added when the site's day rolled over since it was last refreshed
    # (its boundary moved) or with -Tables * (daily full rebuild). Site UTC offsets come from config/site_config.csv.
    $offsets = @{}
    $cfg = Join-Path (Split-Path $PSScriptRoot) "config\site_config.csv"
    if (Test-Path $cfg) { Import-Csv $cfg | ForEach-Object { $offsets[$_.SiteCode] = [double]$_.UTC_Offset_h } }
    $utcNow = if ($NowUtc) { [datetime]::Parse($NowUtc) } else { (Get-Date).ToUniversalTime() }   # -NowUtc: test the day roll
    # 1 transaction per site (+ one for the shared config tables): a network drop on one replica cannot cancel the other sites
    $groups = [ordered]@{ "(config)" = New-Object System.Collections.ArrayList }
    $kinds = @{}
    foreach ($t in $db.Model.Tables) {
        if ($want -notcontains $t.Name) { continue }
        $incremental = @($t.Partitions | Where-Object { $_.Name -like "* - recent" }).Count -gt 0
        foreach ($pt in $t.Partitions) {
            if ($pt.SourceType -ne "M") { continue }
            $site = if ($pt.Name -like "$($t.Name) - *") { $pt.Name.Substring($t.Name.Length + 3) } else { "(config)" }
            $isRecent = $site -like "* - recent"
            if ($isRecent) { $site = $site.Substring(0, $site.Length - 9) }
            if ($Sites -ne "*" -and $site -ne "(config)" -and ($Sites.Split(",") -notcontains $site)) { continue }
            $kind = if (-not $incremental) { "full" } elseif ($isRecent) { "recent" } else { "history" }
            if ($kind -eq "history" -and $Tables -ne "*") {
                # site-local midnight in UTC (+5 min margin: a history evaluated just before midnight is redone)
                $off = if ($offsets.ContainsKey($site)) { $offsets[$site] } else { $null }
                $roll = $true
                if ($null -ne $off) {
                    $localNow = $utcNow.AddHours($off)
                    $midUtc = $localNow.Date.AddMinutes(5).AddHours(-$off)
                    $roll = ($pt.RefreshedTime -lt $midUtc) -or ($pt.RefreshedTime.Year -lt 2000)
                }
                if (-not $roll) { continue }
                $kind = "history (day roll)"
            }
            if (-not $groups.Contains($site)) { $groups[$site] = New-Object System.Collections.ArrayList }
            [void]$groups[$site].Add(@{ database = $db.Name; table = $t.Name; partition = $pt.Name })
            $kinds["$site|$kind"] = 1 + [int]$kinds["$site|$kind"]
        }
    }
    if ($PlanOnly) { foreach ($s in $groups.Keys) { $mix = (@($kinds.Keys | Where-Object { $_ -like "$s|*" } | ForEach-Object { "$($kinds[$_]) $($_.Split('|')[1])" }) -join ", "); Write-Output "PLAN $s : $mix" }; $srv.Disconnect(); continue }
    $t0 = Get-Date; $ok = @(); $bad = @(); $stalled = $false
    foreach ($site in $groups.Keys) {
        $objs = @($groups[$site]); if (-not $objs.Count) { continue }
        # data + recalculation of the calculated tables / columns / relationships in ONE transaction (a sequence commits once):
        # a dataOnly commit alone leaves the model "needing recalculation" and every visual shows "Error fetching data"
        # until a later calculate - visible to users during every cycle
        $tmsl = @{ sequence = @{ maxParallelism = $MaxParallel; operations = @(
            @{ refresh = @{ type = "dataOnly"; objects = $objs } },
            @{ refresh = @{ type = "calculate"; objects = @(@{ database = $db.Name }) } }) } } | ConvertTo-Json -Depth 8 -Compress
        $mix = (@($kinds.Keys | Where-Object { $_ -like "$site|*" } | ForEach-Object { "$($kinds[$_]) $($_.Split('|')[1])" }) -join ", ")
        Write-Output ("[{0}] {1}: refreshing {2} partitions ({3})" -f (Get-Date -Format HH:mm:ss), $site, $objs.Count, $mix)
        for ($try = 1; $try -le $Retries; $try++) {
            $res = Invoke-Watched $srv $tmsl $site $ms.ProcessId
            if ($res -is [string] -and $res -eq "STALLED") { $stalled = $true; $why = if (Get-Process LogonUI -ErrorAction SilentlyContinue) { "workstation locked - sign-in token needs an interactive refresh" } else { "missing Desktop credential?" }; $errs = @("STALLED: no data-source activity for $StallSec s ($why)"); break }
            if ($res -is [string]) { $errs = @($res) }
            else { $errs = @($res | ForEach-Object { $_.Messages } | Where-Object { $_ -is [Microsoft.AnalysisServices.XmlaError] } | ForEach-Object { $_.Description }) }
            if (-not $errs.Count) { break }
            Write-Output ("[{0}] {1}: try {2} failed - {3}" -f (Get-Date -Format HH:mm:ss), $site, $try, ($errs | Select-Object -First 1))
            if ($try -lt $Retries) { Start-Sleep -Seconds (20 * $try) }
        }
        Phase "$site done"
        if ($errs.Count) { $bad += "$site (after $Retries tries): $(($errs | Select-Object -First 2) -join ' | ')" } else { $ok += "$site=$($objs.Count)" }
        if ($stalled) { break }      # the stuck transaction holds the model locks - the next sites would wait behind it
    }
    # safety net: one more calculate after all sites (no-op when every site transaction succeeded); skipped after a stall -
    # it would wait behind the stuck transaction
    if (-not $stalled) {
        $calc = $srv.Execute((@{ refresh = @{ type = "calculate"; objects = @(@{ database = $db.Name }) } } | ConvertTo-Json -Depth 6 -Compress))
        $cerr = @($calc | ForEach-Object { $_.Messages } | Where-Object { $_ -is [Microsoft.AnalysisServices.XmlaError] } | ForEach-Object { $_.Description })
        Phase "calculate pass done"
        if ($cerr.Count) { $bad += "calculate: $(($cerr | Select-Object -First 2) -join ' | ')" }
    }
    $secs = [int]((Get-Date) - $t0).TotalSeconds
    if ($bad.Count) { Write-Output "$($p.MainWindowTitle): PARTIAL after ${secs}s - ok: $($ok -join ', ') | FAILED: $($bad -join ' || ')" }
    else { Write-Output "$($p.MainWindowTitle): refreshed $($ok -join ', ') partitions in ${secs}s" }
    $srv.Disconnect()
    if ($stalled) { exit 4 }
}





