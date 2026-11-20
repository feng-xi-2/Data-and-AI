# Replica vs Power BI - same SQL, row counts

Generated 2026-11-20 13:29 by `py tools/compare_replica_pbi.py` on the open model, sites BINHDUONG, MINHANG, JAKARTA, AKASHI. Each model query is rendered exactly as the model sends it (tools/validate_sql.py), run read-only on the live replica, and its row count compared with COUNTROWS of the table for that site in the model. The queries are in `queries/replica/<SITE>/` and `queries/pbi/`.

Result: **FEATURE_OFF** 14, **LIVE_DRIFT** 28, **LIVE_SNAPSHOT** 1, **MATCH** 66, **M_TRANSFORM** 3

Statuses: MATCH = same rows; LIVE_DRIFT = <= max(5, 1 %) - the live replica moved between refresh and check; LIVE_SNAPSHOT = live-state table rechecked right after a targeted refresh, still moving (pallets in transit); M_TRANSFORM = a Power Query step after the SQL filters / de-duplicates rows by design; FEATURE_OFF = feature not used at the site, 0 rows on purpose.

| Site | Table | Replica rows | Model rows | Status | Reason |
|---|---|---|---|---|---|
| BINHDUONG | Level A Available Pallet Spot | 105 | 104 | LIVE_DRIFT | rechecked right after a targeted refresh: +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Level A Occupied Pallet | 692 | 692 | MATCH | rechecked right after a targeted refresh: same row count |
| BINHDUONG | Outbound Pallet from Inv | 772 | 771 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet cleaned up from bin A | 38478 | 38440 | LIVE_DRIFT | +38 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet From HOFFIN | 62 | 63 | LIVE_DRIFT | rechecked right after a targeted refresh: -1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet From LTA To Level A | 1150 | 1148 | LIVE_DRIFT | +2 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet from LTA to short/tall location | 10 | 11 | LIVE_DRIFT | -1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet in Level A not active shipment | 138 | 137 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallet Pattern | 1200 | 1200 | MATCH |  |
| BINHDUONG | Pallets Location | 7086 | 7086 | MATCH |  |
| BINHDUONG | Pallets Movement | 258036 | 258092 | LIVE_DRIFT | -56 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Planned Pallet PO | 1123 | 2721 | M_TRANSFORM | Power Query step(s) after the SQL change the rows: Table.Distinct, Table.SelectRows |
| BINHDUONG | Planned PO RPM Breakdown | 6491 | 6491 | MATCH |  |
| BINHDUONG | Produced Pallet | 6694 | 6687 | LIVE_DRIFT | +7 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Shipped Pallet | 705 | 704 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Short PO | 2 | 3 | LIVE_DRIFT | -1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | TTAT | 6158 | 6142 | LIVE_DRIFT | +16 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | WorkLine Activities | 63276 | 63244 | LIVE_DRIFT | +32 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Data Health | 2 | 2 | MATCH |  |
| BINHDUONG | Inventory | 179 | 181 | LIVE_DRIFT | -2 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Location Utilisation | 31 | 31 | MATCH |  |
| BINHDUONG | Open Trailers | 11 | 10 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Outbound TTA | 955 | 954 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Pallets In Flow | 511 | 545 | LIVE_SNAPSHOT | rechecked right after a targeted refresh: -34 rows on a live-state table - pallets moved in between (gap = trailer stage 62 vs 105, pallets differing in both directions = turnover, not a query difference) |
| BINHDUONG | Process Edges | 44 | 43 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Shipments | 530 | 531 | LIVE_DRIFT | -1 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | Truck Staging | 2179 | 2173 | LIVE_DRIFT | +6 rows: the live replica moved between the model refresh and this check |
| BINHDUONG | User Activity | 29120 | 29110 | LIVE_DRIFT | +10 rows: the live replica moved between the model refresh and this check |
| MINHANG | Level A Available Pallet Spot | 1062 | 1062 | MATCH |  |
| MINHANG | Level A Occupied Pallet | 1640 | 1640 | MATCH |  |
| MINHANG | Outbound Pallet from Inv | 22 | 22 | MATCH |  |
| MINHANG | Pallet cleaned up from bin A | 0 | 0 | MATCH |  |
| MINHANG | Pallet From HOFFIN |  | 0 | FEATURE_OFF | Has_HOFF = 0 for MINHANG: the model holds no rows on purpose |
| MINHANG | Pallet From LTA To Level A | 12 | 12 | MATCH |  |
| MINHANG | Pallet from LTA to short/tall location | 0 | 0 | MATCH |  |
| MINHANG | Pallet in Level A not active shipment | 765 | 765 | MATCH |  |
| MINHANG | Pallet Pattern | 4334 | 4334 | MATCH |  |
| MINHANG | Pallets Location | 3303 | 3303 | MATCH |  |
| MINHANG | Pallets Movement | 13965 | 13965 | MATCH |  |
| MINHANG | Planned Pallet PO | 67 | 782 | M_TRANSFORM | Power Query step(s) after the SQL change the rows: Table.Distinct, Table.SelectRows |
| MINHANG | Planned PO RPM Breakdown | 229 | 229 | MATCH |  |
| MINHANG | Produced Pallet | 18 | 18 | MATCH |  |
| MINHANG | Shipped Pallet | 18 | 18 | MATCH |  |
| MINHANG | Short PO | 15 | 15 | MATCH |  |
| MINHANG | TTAT | 11 | 11 | MATCH |  |
| MINHANG | WorkLine Activities | 101 | 101 | MATCH |  |
| MINHANG | Data Health | 2 | 2 | MATCH |  |
| MINHANG | Inventory | 60 | 60 | MATCH |  |
| MINHANG | Location Utilisation | 7 | 7 | MATCH |  |
| MINHANG | Open Trailers | 1 | 1 | MATCH |  |
| MINHANG | Outbound TTA | 0 | 0 | MATCH |  |
| MINHANG | Pallets In Flow | 136 | 136 | MATCH |  |
| MINHANG | Process Edges | 20 | 20 | MATCH |  |
| MINHANG | Shipments | 0 | 0 | MATCH |  |
| MINHANG | Truck Staging | 7 | 7 | MATCH |  |
| MINHANG | User Activity | 351 | 351 | MATCH |  |
| JAKARTA | Level A Available Pallet Spot | 1144 | 1144 | MATCH |  |
| JAKARTA | Level A Occupied Pallet | 765 | 765 | MATCH |  |
| JAKARTA | Outbound Pallet from Inv | 665 | 664 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| JAKARTA | Pallet cleaned up from bin A | 1150 | 1150 | MATCH |  |
| JAKARTA | Pallet From HOFFIN |  | 0 | FEATURE_OFF | Has_HOFF = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Pallet From LTA To Level A | 0 | 0 | MATCH |  |
| JAKARTA | Pallet from LTA to short/tall location |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Pallet in Level A not active shipment | 7 | 7 | MATCH |  |
| JAKARTA | Pallet Pattern | 14496 | 14496 | MATCH |  |
| JAKARTA | Pallets Location | 101 | 101 | MATCH |  |
| JAKARTA | Pallets Movement | 235227 | 235323 | LIVE_DRIFT | -96 rows: the live replica moved between the model refresh and this check |
| JAKARTA | Planned Pallet PO |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Planned PO RPM Breakdown |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Produced Pallet |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Shipped Pallet | 500 | 500 | MATCH |  |
| JAKARTA | Short PO |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | TTAT | 55203 | 55203 | MATCH |  |
| JAKARTA | WorkLine Activities |  | 0 | FEATURE_OFF | Has_Production = 0 for JAKARTA: the model holds no rows on purpose |
| JAKARTA | Data Health | 2 | 2 | MATCH |  |
| JAKARTA | Inventory | 215 | 215 | MATCH |  |
| JAKARTA | Location Utilisation | 60 | 60 | MATCH |  |
| JAKARTA | Open Trailers | 15 | 15 | MATCH |  |
| JAKARTA | Outbound TTA | 1586 | 1586 | MATCH |  |
| JAKARTA | Pallets In Flow | 512 | 512 | MATCH |  |
| JAKARTA | Process Edges | 52 | 52 | MATCH |  |
| JAKARTA | Shipments | 4012 | 4012 | MATCH |  |
| JAKARTA | Truck Staging | 993 | 995 | LIVE_DRIFT | -2 rows: the live replica moved between the model refresh and this check |
| JAKARTA | User Activity | 9676 | 9680 | LIVE_DRIFT | -4 rows: the live replica moved between the model refresh and this check |
| AKASHI | Level A Available Pallet Spot |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Level A Occupied Pallet |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Outbound Pallet from Inv |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Pallet cleaned up from bin A |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Pallet From HOFFIN | 0 | 0 | MATCH |  |
| AKASHI | Pallet From LTA To Level A |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Pallet from LTA to short/tall location | 0 | 0 | MATCH |  |
| AKASHI | Pallet in Level A not active shipment |  | 0 | FEATURE_OFF | Has_LevelA = 0 for AKASHI: the model holds no rows on purpose |
| AKASHI | Pallet Pattern | 3416 | 3416 | MATCH |  |
| AKASHI | Pallets Location | 5575 | 5575 | MATCH |  |
| AKASHI | Pallets Movement | 17981 | 17962 | LIVE_DRIFT | +19 rows: the live replica moved between the model refresh and this check |
| AKASHI | Planned Pallet PO | 30 | 18 | M_TRANSFORM | Power Query step(s) after the SQL change the rows: Table.Distinct, Table.SelectRows |
| AKASHI | Planned PO RPM Breakdown | 288 | 288 | MATCH |  |
| AKASHI | Produced Pallet | 1 | 1 | MATCH |  |
| AKASHI | Shipped Pallet | 4 | 4 | MATCH |  |
| AKASHI | Short PO | 0 | 0 | MATCH |  |
| AKASHI | TTAT | 0 | 0 | MATCH |  |
| AKASHI | WorkLine Activities | 35 | 34 | LIVE_DRIFT | +1 rows: the live replica moved between the model refresh and this check |
| AKASHI | Data Health | 2 | 2 | MATCH |  |
| AKASHI | Inventory | 175 | 175 | MATCH |  |
| AKASHI | Location Utilisation | 47 | 47 | MATCH |  |
| AKASHI | Open Trailers | 5 | 5 | MATCH |  |
| AKASHI | Outbound TTA | 1 | 1 | MATCH |  |
| AKASHI | Pallets In Flow | 51 | 48 | LIVE_DRIFT | +3 rows: the live replica moved between the model refresh and this check |
| AKASHI | Process Edges | 21 | 21 | MATCH |  |
| AKASHI | Shipments | 37 | 37 | MATCH |  |
| AKASHI | Truck Staging | 6 | 6 | MATCH |  |
| AKASHI | User Activity | 47 | 44 | LIVE_DRIFT | +3 rows: the live replica moved between the model refresh and this check |
