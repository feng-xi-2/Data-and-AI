<#  Run a batch of DAX queries against the open Power BI Desktop model (one connection) - Windows PowerShell 5.1.
    powershell -File run_dax_batch.ps1 -ProcId <PBIDesktop PID> -InJson queries.json -OutJson results.json [-TimeoutSec 60]
    queries.json = [ { "id": "...", "dax": "EVALUATE ..." }, ... ]
    results.json = [ { "id", "rows", "first" (first row, column -> value), "error", "ms" }, ... ]
    Heartbeat: one progress line at least every 30 s; every result is also appended to <OutJson>.jsonl as it arrives
    (opened shared: reading it while the batch runs never blocks the batch); a lost connection is reopened and reported (never silent).
    <OutJson>.lock holds the PID of the running batch: a second batch on the same output stops with exit 5 instead of
    interleaving results (a replay whose shell was closed can keep running as an orphan). #>
param([int]$ProcId, [string]$InJson, [string]$OutJson, [int]$TimeoutSec = 60, [int]$HeartbeatSec = 30)
$ErrorActionPreference = "Stop"
function Say($m) { Write-Output ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $m); [Console]::Out.Flush() }
try {
    $p = Get-Process -Id $ProcId
    Add-Type -Path (Join-Path (Split-Path $p.Path) "Microsoft.PowerBI.AdomdClient.dll")
    $ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
    if (-not $ms) { throw "no Analysis Services engine under PBIDesktop $ProcId" }
    $port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
} catch { Say "FATAL: $($_.Exception.Message)"; exit 2 }
function Open-Cn { $c = New-Object Microsoft.AnalysisServices.AdomdClient.AdomdConnection("Data Source=localhost:$port"); $c.Open(); return $c }
$cn = Open-Cn
$qs = @((Get-Content $InJson -Raw -Encoding UTF8 | ConvertFrom-Json) | ForEach-Object { $_ })   # PS 5.1 returns a JSON array as ONE object -> unroll
if ($qs.Count -eq 0 -or -not $qs[0].dax) { Say "FATAL: no queries read from $InJson"; exit 4 }
$lock = "$OutJson.lock"
if (Test-Path $lock) {
    $other = 0; [void][int]::TryParse(([string](Get-Content $lock -Raw)).Trim(), [ref]$other)
    $op = if ($other -and $other -ne $PID) { Get-CimInstance Win32_Process -Filter "ProcessId=$other" -ErrorAction SilentlyContinue }
    if ($op -and $op.CommandLine -match 'run_dax_batch') {
        Say "FATAL: another DAX batch (PID $other) is still writing $OutJson - wait for it or stop it (Stop-Process -Id $other)"; exit 5
    }
}
Set-Content $lock $PID
$jsonl = "$OutJson.jsonl"
$jw = New-Object System.IO.StreamWriter([System.IO.File]::Open($jsonl, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite), (New-Object System.Text.UTF8Encoding($false)))
$jw.AutoFlush = $true
$out = New-Object System.Collections.ArrayList
$total = @($qs).Length; $i = 0; $nerr = 0; $nempty = 0; $slow = 0; $slowId = ""
$tStart = Get-Date; $tBeat = Get-Date
# each query runs in a worker runspace so the heartbeat keeps printing while one long query is still executing
$worker = {
    param($cn, $dax, $to)
    $ErrorActionPreference = "Stop"
    $c = $cn.CreateCommand(); $c.CommandText = $dax; $c.CommandTimeout = $to
    $r = $c.ExecuteReader(); $n = 0; $f = $null
    $sb = New-Object System.Text.StringBuilder
    while ($r.Read()) {
        if ($n -eq 0) { $f = [ordered]@{}; for ($k = 0; $k -lt $r.FieldCount; $k++) { $v = $r.GetValue($k); if ($v -is [datetime]) { $v = $v.ToString("yyyy-MM-dd HH:mm") }; $f[$r.GetName($k)] = $v } }
        for ($k = 0; $k -lt $r.FieldCount; $k++) { [void]$sb.Append([string]$r.GetValue($k)).Append([char]31) }
        [void]$sb.Append([char]30)
        $n++
    }
    $r.Close()
    # fingerprint of the WHOLE result (all rows / values): lets tests check that a visual changes with the day / site filter
    $sha = [System.Security.Cryptography.SHA1]::Create()
    $hash = -join ($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($sb.ToString())) | Select-Object -First 8 | ForEach-Object { $_.ToString("x2") })
    @{ rows = $n; first = $f; hash = $hash }
}
$rs = [runspacefactory]::CreateRunspace(); $rs.Open()
function Beat($extra) {
    $el = ((Get-Date) - $tStart).TotalSeconds; $eta = if ($i -gt 1) { [int]($el / ($i - 1) * ($total - $i + 1)) } else { 0 }
    Say "heartbeat: $($i - 1)/$total done, errors $nerr, 0-row $nempty, slowest ${slow}ms (q$slowId), ETA ${eta}s$extra"
    $script:tBeat = Get-Date
}
Say "start: $total queries on localhost:$port (timeout ${TimeoutSec}s each)"
foreach ($q in $qs) {
    $i++
    $t0 = Get-Date
    $o = [ordered]@{ id = $q.id; rows = $null; first = $null; hash = $null; error = $null; ms = 0 }
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        $ps = [powershell]::Create(); $ps.Runspace = $rs
        [void]$ps.AddScript($worker).AddArgument($cn).AddArgument($q.dax).AddArgument($TimeoutSec)
        $h = $ps.BeginInvoke()
        while (-not $h.AsyncWaitHandle.WaitOne(1000)) {
            if (((Get-Date) - $tBeat).TotalSeconds -ge $HeartbeatSec) { Beat ", running q$($q.id) for $([int]((Get-Date) - $t0).TotalSeconds)s" }
        }
        try {
            $res = @($ps.EndInvoke($h))
            if ($ps.Streams.Error.Count -gt 0) { throw $ps.Streams.Error[0].Exception }
            $o.rows = $res[-1].rows; $o.first = $res[-1].first; $o.hash = $res[-1].hash; $o.error = $null
            $ps.Dispose()
            break
        } catch {
            $ps.Dispose()
            $e = $_.Exception; while ($e.InnerException) { $e = $e.InnerException }
            $msg = $e.Message
            $o.error = $msg.Substring(0, [Math]::Min(400, $msg.Length))
            if ($cn.State -ne "Open" -or $msg -match "connection|transport|forcibly") {
                Say "connection lost at query $($q.id) - reconnecting ($msg)"
                try { $cn.Close() } catch {}
                try { $cn = Open-Cn } catch { Say "FATAL: cannot reconnect: $($_.Exception.Message)"; exit 3 }
            } else { break }
        }
    }
    $o.ms = [int]((Get-Date) - $t0).TotalMilliseconds
    if ($o.error) { $nerr++; Say "query $($q.id) ERROR after $($o.ms) ms: $($o.error.Substring(0, [Math]::Min(160, $o.error.Length)))" } elseif (-not $o.rows) { $nempty++ }
    if ($o.ms -gt $slow) { $slow = $o.ms; $slowId = $q.id }
    [void]$out.Add($o)
    try { $jw.WriteLine((ConvertTo-Json -InputObject $o -Depth 5 -Compress)) }
    catch { Say "WARNING: progress file $jsonl not written for q$($q.id) ($($_.Exception.Message)) - the result is kept in memory" }
    if (((Get-Date) - $tBeat).TotalSeconds -ge $HeartbeatSec) { $i++; Beat ""; $i-- }
}
$rs.Close()
$cn.Close()
$jw.Close()
ConvertTo-Json -InputObject @($out) -Depth 5 | Set-Content $OutJson -Encoding UTF8
Remove-Item $lock -ErrorAction SilentlyContinue
Say "done: $total queries in $([int]((Get-Date) - $tStart).TotalSeconds)s, errors $nerr, 0-row $nempty"



