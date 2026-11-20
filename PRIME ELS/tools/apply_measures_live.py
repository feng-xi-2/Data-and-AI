"""Push measure definitions from a freshly built TMDL (_KPI.tmdl) into the model open in Power BI Desktop - no rebuild / reload /
refresh needed for DAX-only fixes. The PBIP on disk stays the source of truth: rebuild with tools/build_pbip.py afterwards.

    py tools/apply_measures_live.py <PBIDesktop pid> "<Measure A>|<Measure B>" [--tmdl dist/BINHDUONG/.../_KPI.tmdl]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def measures_from_tmdl(path):
    t = path.read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r"(?m)^\tmeasure ('(?:[^']|'')+'|[^\s=]+) = ```\n(.*?)\n\t\t\t```\n((?:\t\t[^\n]*\n)*)", t, re.S):
        name = m.group(1).strip("'").replace("''", "'")
        dax = "\n".join(ln[3:] if ln.startswith("\t\t\t") else ln for ln in m.group(2).splitlines())
        fmt = re.search(r"(?m)^\t\tformatString: (.*)$", m.group(3))
        out[name] = {"expr": dax, "fmt": fmt.group(1) if fmt else None}
    return out


def main(argv):
    pid, names = int(argv[0]), [n for n in argv[1].split("|") if n]
    tmdl = Path(argv[argv.index("--tmdl") + 1]) if "--tmdl" in argv else next((ROOT / "dist" / "BINHDUONG").glob("*.SemanticModel/definition/tables/_KPI.tmdl"))
    defs = measures_from_tmdl(tmdl)
    missing = [n for n in names if n not in defs]
    if missing:
        raise SystemExit(f"FAILED: not in {tmdl}: {missing}")
    payload = ROOT.parent / "_uitest" / "_apply_measures.json"
    payload.parent.mkdir(exist_ok=True)
    payload.write_text(json.dumps([{"name": n, **defs[n]} for n in names]), encoding="utf-8")
    ps = r"""
param([int]$ProcId, [string]$Json)
$ErrorActionPreference = "Stop"
foreach ($d in "Microsoft.AnalysisServices.Core.dll", "Microsoft.AnalysisServices.Tabular.Json.dll", "Microsoft.AnalysisServices.Tabular.dll") { Add-Type -Path (Join-Path "%AMO%" $d) }
$ms = Get-CimInstance Win32_Process -Filter "Name='msmdsrv.exe' AND ParentProcessId=$ProcId"
$port = (Get-NetTCPConnection -OwningProcess $ms.ProcessId -State Listen | Select-Object -First 1).LocalPort
$srv = New-Object Microsoft.AnalysisServices.Tabular.Server; $srv.Connect("Data Source=localhost:$port")
$db = $srv.Databases[0]; $kpi = $db.Model.Tables["_KPI"]
$items = Get-Content $Json -Raw -Encoding UTF8 | ConvertFrom-Json
foreach ($it in @($items | ForEach-Object { $_ })) {
    $m = $kpi.Measures[$it.name]
    if (-not $m) { $m = New-Object Microsoft.AnalysisServices.Tabular.Measure; $m.Name = $it.name; $kpi.Measures.Add($m); Write-Output "added $($it.name)" }
    $m.Expression = $it.expr
    if ($it.fmt) { $m.FormatString = ($it.fmt.Trim('"') -replace '""', '"') }
    Write-Output "updated $($it.name)"
}
$db.Model.SaveChanges() | Out-Null
foreach ($it in @($items | ForEach-Object { $_ })) { $m = $kpi.Measures[$it.name]; if ($m.ErrorMessage) { Write-Output "ERROR $($it.name): $($m.ErrorMessage)" } else { Write-Output "ok $($it.name)" } }
$srv.Disconnect()
""".replace("%AMO%", str(HERE / "amo"))
    script = ROOT.parent / "_uitest" / "_apply_measures.ps1"
    script.write_text(ps, encoding="utf-8")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-ProcId", str(pid), "-Json", str(payload)],
                       capture_output=True, text=True, timeout=300)
    print(r.stdout.strip() or r.stderr.strip())
    sys.exit(0 if r.returncode == 0 and "ERROR" not in r.stdout and "MISSING" not in r.stdout else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
