"""Read/write the graph as one JSON list or as shards (relationships/parts/<kind>_NNN.json, each < 1.9 MB - the public repo's
publish check blocks files over 2 MB)."""
import glob
import json
import os

KIT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIMIT = 1_900_000


def load(kind, folder=None):
    folder = folder or os.path.join(KIT, "relationships")
    single = os.path.join(folder, f"{kind}.json")
    if os.path.exists(single):
        return json.load(open(single, encoding="utf-8"))
    out = []
    for f in sorted(glob.glob(os.path.join(folder, "parts", f"{kind}_*.json"))):
        out += json.load(open(f, encoding="utf-8"))
    if not out:
        raise SystemExit(f"no {kind}.json or parts/{kind}_*.json in {folder}")
    return out


def shard(items, folder, kind):
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, f"{kind}_*.json")):
        os.remove(f)
    part, size, n = [], 2, 0
    for it in items:
        s = len(json.dumps(it, ensure_ascii=False).encode()) + 2
        if part and size + s > LIMIT:
            json.dump(part, open(os.path.join(folder, f"{kind}_{n:03d}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            part, size, n = [], 2, n + 1
        part.append(it)
        size += s
    if part:
        json.dump(part, open(os.path.join(folder, f"{kind}_{n:03d}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        n += 1
    return n
