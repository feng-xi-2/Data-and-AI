"""Build the share packages from dist/ (run after build_pbip.py and the tests).

    py tools/make_packages.py

dist/_share/WH Hypercare KPI - <SITE>.zip                 the site file for colleagues (one site, Desktop incremental partitions)
dist/_share/service/WH Hypercare KPI - <SITE> (Service).zip   the Power BI Service variant (incremental refresh policies)
PRIME_ELS_Hypercare_KPI_Kit.zip                            the whole kit (config, sql, tools, docs, skill, theme, source, dist)
Local / secret files are never packed: .pbi caches and local settings, tools/amo, logs, locks, token caches, _validate_*.json.
"""
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {".pbi", "__pycache__", "amo", "_share", ".git"}
SKIP_NAMES = {"refresh.lock", "_auto_refresh.log", "cache.abf", "localSettings.json"}
SKIP_SUFFIX = (".log", ".pyc", ".lock")


def keep(p: Path):
    # the original BD pbix and its DataModel hold BD data (97 MB) - the build only needs _src_oct/tmdl_original + pbix/Report
    if p.suffix.lower() == ".pbix" or (len(p.parts) >= 2 and p.parts[-1] == "DataModel"):
        return False
    return not (set(p.parts) & SKIP_PARTS) and p.name not in SKIP_NAMES and not p.name.endswith(SKIP_SUFFIX) \
        and not p.name.startswith(("_validate_", "_q_", "_r_")) and "token" not in p.name.lower()


def pack(src: Path, zip_path: Path, top: str):
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(src.rglob("*")):
            if f.is_file() and keep(f.relative_to(src)):
                z.write(f, f"{top}/{f.relative_to(src).as_posix()}")
                n += 1
    print(f"{time.strftime('[%H:%M:%S]')} {zip_path.relative_to(ROOT)}: {n} files, {zip_path.stat().st_size / 1e6:.1f} MB", flush=True)


for d in sorted((ROOT / "dist").iterdir()):
    if d.is_dir() and not d.name.startswith("_") and d.name != "ALL_SITES":
        pack(d, ROOT / "dist" / "_share" / f"WH Hypercare KPI - {d.name}.zip", f"WH Hypercare KPI - {d.name}")
for d in sorted((ROOT / "dist" / "_service").iterdir()) if (ROOT / "dist" / "_service").exists() else []:
    pack(d, ROOT / "dist" / "_share" / "service" / f"WH Hypercare KPI - {d.name} (Service).zip", f"WH Hypercare KPI - {d.name} (Service)")
kit = ROOT / "PRIME_ELS_Hypercare_KPI_Kit.zip"
tmp = ROOT.parent / "_kit_tmp.zip"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    n = 0
    for f in sorted(ROOT.rglob("*")):
        rel = f.relative_to(ROOT)
        if f.is_file() and f != kit and keep(rel) and rel.parts[0] in ("_src_oct", "config", "dist", "docs", "skill", "sql", "theme", "tools", "README.md"):
            z.write(f, f"PRIME_ELS_Hypercare_KPI_Kit/{rel.as_posix()}")
            n += 1
tmp.replace(kit)
print(f"{time.strftime('[%H:%M:%S]')} {kit.name}: {n} files, {kit.stat().st_size / 1e6:.1f} MB")
