<#  Run a long command with a heartbeat: prints the command's own output as it arrives and, at least every 30 s,
    "[hh:mm:ss] heartbeat: <label> running <n> s". A non-zero exit or an exception is reported, never swallowed.
    powershell -File with_heartbeat.ps1 -Label "refresh" -Exe powershell.exe -ArgLine "-NoProfile -File x.ps1" #>
param([string]$Label, [string]$Exe, [string]$ArgLine, [int]$EverySec = 30, [string]$WorkDir = $PWD.Path)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $Exe
$psi.Arguments = $ArgLine
$psi.WorkingDirectory = $WorkDir
$psi.UseShellExecute = $false; $psi.RedirectStandardOutput = $true; $psi.RedirectStandardError = $true
$p = New-Object System.Diagnostics.Process; $p.StartInfo = $psi
$null = $p.Start()
$t0 = Get-Date; $tb = Get-Date
$outTask = $p.StandardOutput.ReadLineAsync(); $errTask = $p.StandardError.ReadLineAsync()
Write-Output ("[{0}] start: {1}" -f (Get-Date -Format HH:mm:ss), $Label)
while ($true) {
    $did = $false
    if ($outTask.IsCompleted) { if ($null -ne $outTask.Result) { Write-Output $outTask.Result; $outTask = $p.StandardOutput.ReadLineAsync(); $did = $true } }
    if ($errTask.IsCompleted) { if ($null -ne $errTask.Result) { Write-Output ("STDERR: " + $errTask.Result); $errTask = $p.StandardError.ReadLineAsync(); $did = $true } }
    if ($p.HasExited -and $outTask.IsCompleted -and $null -eq $outTask.Result -and $errTask.IsCompleted -and $null -eq $errTask.Result) { break }
    if (((Get-Date) - $tb).TotalSeconds -ge $EverySec) {
        Write-Output ("[{0}] heartbeat: {1} running {2} s" -f (Get-Date -Format HH:mm:ss), $Label, [int]((Get-Date) - $t0).TotalSeconds); $tb = Get-Date
    }
    if (-not $did) { Start-Sleep -Milliseconds 300 }
}
$p.WaitForExit()
Write-Output ("[{0}] end: {1} exit {2} after {3} s" -f (Get-Date -Format HH:mm:ss), $Label, $p.ExitCode, [int]((Get-Date) - $t0).TotalSeconds)
exit $p.ExitCode

