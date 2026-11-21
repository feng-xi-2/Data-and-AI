"""Push the Power Query (M) of chosen tables from sql/ + config/ into the OPEN Power BI Desktop model - no reopen, no full refresh.

    py tools/sync_partitions.py <PBIDesktop PID> "Inventory|Process Edges"

 1. builds dist/ALL_SITES into a temp folder (same generator, same gates as build_pbip.py),
 2. sends every partition's M of those tables to the open model (sync_partitions.ps1; unchanged partitions are skipped),
 3. copies the tables' TMDL into dist/ALL_SITES so the files on disk match the open model.
 Then refresh just those tables:  powershell -File tools/refresh_desktop.ps1 -Tables "Inventory"
 Single-site and Service files are NOT touched - rebuild them with build_pbip.py <SITE> / --service."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import build_pbip as B

TOOLS = Path(__file__).resolve().parent


def table_files(defn):
    """real table name -> TMDL file of a built SemanticModel/definition folder."""
    out = {}
    for f in (defn / "tables").glob("*.tmdl"):
        m = re.search(r"(?m)^table (.+)$", f.read_text(encoding="utf-8"))
        name = m.group(1).strip()
        out[name[1:-1].replace("''", "'") if name.startswith("'") else name] = f
    return out


def partitions(text):
    for m in B.PART_RX.finditer(text):
        name = re.match(r"\tpartition (.+) = m\n", m.group(1)).group(1).strip()
        yield (name[1:-1].replace("''", "'") if name.startswith("'") else name), B.dedent_m(m.group(2))


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    pid, wanted = int(argv[0]), [t.strip() for t in argv[1].split("|") if t.strip()]
    tmp = B.ROOT / "_sync_build"
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        print(f"building ALL_SITES into {tmp.name} ...", flush=True)
        B.build_one("ALL SITES (partition sync)", tmp, B.PRODUCT, None)
        built = table_files(tmp / f"{B.PRODUCT}.SemanticModel" / "definition")
        disk = table_files(B.ROOT / "dist" / "ALL_SITES" / f"{B.PRODUCT}.SemanticModel" / "definition")
        items = []
        for t in wanted:
            if t not in built:
                raise SystemExit(f"FAILED: table {t!r} is not in the build")
            parts = list(partitions(built[t].read_text(encoding="utf-8")))
            if not parts:
                raise SystemExit(f"FAILED: no M partition found in {built[t].name}")
            items += [{"table": t, "partition": p, "expression": e} for p, e in parts]
            print(f"  {t}: {len(parts)} partition(s)", flush=True)
        js = tmp / "partitions.json"
        js.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "sync_partitions.ps1"),
                            "-ProcId", str(pid), "-Json", str(js)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stdout + r.stderr).strip(), flush=True)
        if r.returncode or "saved" not in r.stdout:
            raise SystemExit(f"FAILED: sync_partitions.ps1 exit {r.returncode} - open model NOT changed, dist/ALL_SITES NOT changed")
        for t in wanted:
            dst = disk.get(t) or (B.ROOT / "dist" / "ALL_SITES" / f"{B.PRODUCT}.SemanticModel" / "definition" / "tables" / built[t].name)
            shutil.copyfile(built[t], dst)
            print(f"  dist/ALL_SITES updated: {dst.name}", flush=True)
        print(f"done - now refresh: powershell -File tools/refresh_desktop.ps1 -Tables \"{'|'.join(wanted)}\"", flush=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1:])
