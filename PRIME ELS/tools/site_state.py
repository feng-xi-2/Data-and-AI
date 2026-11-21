"""Source state per site from the model's own Data Health table (dlytrn first / last event at the last refresh).

An EMPTY replica or one that is not live yet (< MIN_HISTORY_H of transactions) explains empty tables and visuals at that site:
the report shows it on Config & Health (feed completeness / health checks); the test tools classify it instead of calling it a defect.
Same 72 h rule as tools/profile_site.py.
"""
import re
from datetime import datetime

MIN_HISTORY_H = 72
QUERY = ("EVALUATE SELECTCOLUMNS(FILTER('Data Health', 'Data Health'[Source_Object] = \"dlytrn\"), \"s\", 'Data Health'[SiteCode], "
         "\"f\", 'Data Health'[First_Event_Local], \"l\", 'Data Health'[Last_Event_Local])")


def _dt(v):
    m = re.search(r"Date\((-?\d+)", str(v))
    if m:
        return datetime.fromtimestamp(int(m.group(1)) / 1000)          # ADOMD JSON serialises the stored value as machine-local time
    return datetime.strptime(str(v).replace("T", " ")[:19], "%Y-%m-%d %H:%M:%S")


def source_state(rows):
    """rows = result of QUERY -> {SiteCode: reason} for sites whose replica is empty / not live; live sites are absent."""
    state = {}
    for h in rows:
        f_, l_ = h.get("[f]"), h.get("[l]")
        if not l_:
            state[h["[s]"]] = "SOURCE_EMPTY: the replica holds no transactions (dlytrn empty at the last refresh)"
            continue
        try:
            fd, ld = _dt(f_), _dt(l_)
        except (ValueError, TypeError):
            continue
        hrs = (ld - fd).total_seconds() / 3600
        if hrs < MIN_HISTORY_H:
            state[h["[s]"]] = f"SITE_NOT_LIVE: only {hrs:.0f} h of transactions in the replica ({fd:%Y-%m-%d %H:%M} -> {ld:%Y-%m-%d %H:%M})"
    return state
