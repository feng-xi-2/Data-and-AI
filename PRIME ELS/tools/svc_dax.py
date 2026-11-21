"""DAX against a PUBLISHED model (Power BI REST executeQueries) - the Service counterpart of run_dax_batch.ps1 / pbi_dax.ps1.

    from svc_dax import Svc
    s = Svc("<workspaceId>/<datasetId>")
    s.query('EVALUATE ...')                 -> {"rows", "first", "hash", "ms"[, "error"]}
    s.rows('EVALUATE ...')                  -> list of row dicts (raises on error)
    s.batch([{"id", "dax"}, ...], tag)       -> {id: result} (4 in parallel, heartbeat every 30 s, retries 429 / network drops)
Model metadata (tables / columns / data types) comes from the TMDL of the published build - INFO.* functions are refused by executeQueries.
"""
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DT_CODE = {"string": 2, "int64": 6, "double": 8, "dateTime": 9, "decimal": 10, "boolean": 11}


class Svc:
    def __init__(self, ws_ds, timeout=120, parallel=4):
        self.ws, self.ds = ws_ds.split("/")
        self.timeout, self.parallel = int(timeout), parallel
        self._tok, self._at = None, 0

    def _token(self):
        if time.time() - self._at > 1800:
            from publish import token
            self._tok, self._at = token("https://analysis.windows.net/powerbi/api/.default"), time.time()
        return self._tok

    def query(self, dax, all_rows=False):
        url = f"https://api.powerbi.com/v1.0/myorg/groups/{self.ws}/datasets/{self.ds}/executeQueries"
        t0, err = time.time(), "HTTP 429"
        for attempt in range(6):
            try:
                r = requests.post(url, headers={"Authorization": "Bearer " + self._token()}, timeout=self.timeout + 60,
                                  json={"queries": [{"query": dax}], "serializerSettings": {"includeNulls": True}})
            except requests.RequestException as e:
                err = f"network: {type(e).__name__}"
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "20")))
                continue
            ms = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                try:
                    e = r.json().get("error", {})
                    det = e.get("pbi.error", {}).get("details", [])
                    msg = next((d.get("detail", {}).get("value") for d in det if d.get("code") == "DetailsMessage"), None) or e.get("message") or r.text
                except ValueError:
                    msg = r.text
                if "An error has occurred" in str(msg) and attempt < 4:      # transient Service error (seen 21-Nov): retry with back-off
                    time.sleep(5 * (attempt + 1))
                    continue
                return {"rows": 0, "first": None, "error": str(msg)[:400], "ms": ms}
            res = r.json()["results"][0]
            if res.get("error"):
                if "An error has occurred" in json.dumps(res["error"]) and attempt < 4:
                    time.sleep(5 * (attempt + 1))
                    continue
                return {"rows": 0, "first": None, "error": json.dumps(res["error"])[:400], "ms": ms}
            rows = res["tables"][0].get("rows", []) if res.get("tables") else []
            blob = "\x1e".join("\x1f".join("" if v is None else str(v) for v in row.values()) for row in rows)
            return {"rows": len(rows), "first": rows[0] if rows else None, "ms": ms,
                    "hash": hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16], **({"all": rows} if all_rows else {})}
        return {"rows": 0, "first": None, "error": f"executeQueries failed after retries ({err})", "ms": int((time.time() - t0) * 1000)}

    def rows(self, dax):
        r = self.query(dax, all_rows=True)
        if r.get("error"):
            raise SystemExit(f"!! query failed: {r['error']}")
        return r["all"]

    def batch(self, queries, tag=""):
        out, t0, beat, nerr = {}, time.time(), time.time(), 0
        self._token()
        with ThreadPoolExecutor(self.parallel) as ex:
            futs = {ex.submit(self.query, q["dax"]): q["id"] for q in queries}
            for i, f in enumerate(as_completed(futs), 1):
                out[futs[f]] = dict(f.result(), id=futs[f])
                nerr += bool(out[futs[f]].get("error"))
                if time.time() - beat > 30:
                    print(f"[{time.strftime('%H:%M:%S')}] {tag} heartbeat: {i}/{len(queries)} done, errors {nerr} ({time.time() - t0:.0f}s)", flush=True)
                    beat = time.time()
        return out


def tmdl_columns(model_dir):
    """[(table, column, ExplicitDataType code)] of the data / calculated-table columns of a built model (INFO.COLUMNS replacement)."""
    out = []
    for f in sorted((Path(model_dir) / "definition" / "tables").glob("*.tmdl")):
        t = f.read_text(encoding="utf-8")
        tn = next(ln[6:].strip().strip("'").replace("''", "'") for ln in t.splitlines() if ln.startswith("table "))
        for m in re.finditer(r"(?m)^\tcolumn ('(?:[^']|'')+'|[^\s=]+)[^\n]*\n((?:\t\t[^\n]*\n|[ \t]*\n)*?)(?=^\t[^\t]|\Z)", t):
            dt = re.search(r"\t\tdataType: (\w+)", m.group(2))
            out.append((tn, m.group(1).strip("'").replace("''", "'"), DT_CODE.get(dt.group(1), 2) if dt else 0))   # 0 = type not declared
    return out
