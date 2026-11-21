# Site tokens used by the query templates

Engine tokens (schema, zone column, ...) are already filled per folder. Site tokens come from the site's row in the
Sites tab / `config/site_config.csv` of the kit and are measured from the replica by `tools/profile_site.py` (see
`skills/hypercare-site-setup/references/settings.md`).

| Token | In site_config | Used by |
|---|---|---|
| `{ACT_DAYS}` | yes | Shipments, User Activity |
| `{AREA_RDTS}` | yes | Pallets Location, Truck Staging |
| `{DETAIL_DAYS}` | yes | Truck Staging |
| `{FG_PRTNUM_LIKE}` | yes | Inventory, PROD_PALLETS, Pallet Pattern, Pallets Location, Planned PO RPM Breakdown |
| `{FROM}` | derived / default (Cfg_Engine, build) | ACTIVE_USERS, PROD_PALLETS, TTAT_IN, TTAT_OUT, USER_PROD |
| `{INC_FROM}` | derived / default (Cfg_Engine, build) | Pallets Movement |
| `{INC_TO}` | derived / default (Cfg_Engine, build) | Pallets Movement |
| `{LOC_EOL}` | yes | Pallets Location |
| `{LOC_EOL_EXACT}` | yes | Pallets Location |
| `{LOC_HOFF_IN}` | yes | HOFF_IN, Pallets Location |
| `{LOC_HOFF_OUT}` | yes | Pallets Location |
| `{LOC_LEVEL_A}` | yes | LVLA_UTIL, Location Utilisation, Pallets Location |
| `{LOC_LTA}` | yes | LTA_QUEUE |
| `{LOC_TRAILER}` | yes | Inventory, Truck Staging |
| `{MOVEMENT_DAYS}` | yes | Pallets Movement, Process Edges |
| `{MOVE_CLASS_CASE}` | derived / default (Cfg_Engine, build) | Process Edges, User Activity |
| `{MOVE_EXCLUDE_LIST}` | derived / default (Cfg_Engine, build) | Process Edges, User Activity |
| `{MOVE_IN_LIST}` | derived / default (Cfg_Engine, build) | Process Edges |
| `{MOVE_PUTAWAY_STEP}` | derived / default (Cfg_Engine, build) | Process Edges |
| `{MOVE_SIDE_LIST}` | derived / default (Cfg_Engine, build) | Process Edges |
| `{PALLET_STAGE_CASE}` | derived / default (Cfg_Engine, build) | Pallets In Flow |
| `{PROD_LEFT_REF}` | derived / default (Cfg_Engine, build) | PROD_PALLETS |
| `{PROD_TXN_FILTER}` | yes | PROD_PALLETS |
| `{PRTDSC_LOCALE}` | yes | Inventory, Open Trailers, Pallets Location, Planned PO RPM Breakdown, Shipments |
| `{SHIPMENT_OPEN_CASE}` | derived / default (Cfg_Engine, build) | Process Edges, Shipments |
| `{SHIPMENT_SINCE_CASE}` | derived / default (Cfg_Engine, build) | Shipments |
| `{SHIPMENT_STAGE_CASE}` | derived / default (Cfg_Engine, build) | Shipments |
| `{SNAP}` | derived / default (Cfg_Engine, build) | TTAT_OUT |
| `{START_DT}` | derived / default (Cfg_Engine, build) | Open Trailers, Outbound TTA, Pallets In Flow, Shipments, TTAT |
| `{STOCK_AGE_CASE}` | derived / default (Cfg_Engine, build) | Inventory |
| `{TALL_HEIGHT_CM}` | yes | Location Utilisation |
| `{TO}` | derived / default (Cfg_Engine, build) | ACTIVE_USERS, PROD_PALLETS, TTAT_IN, TTAT_OUT, USER_PROD |
| `{TRAILER_STAGE_CASE}` | derived / default (Cfg_Engine, build) | Open Trailers, Pallets In Flow |
| `{USR_EXCLUDE}` | yes | ACTIVE_USERS, USER_PROD, User Activity |
| `{WH_ID}` | yes | ACTIVE_USERS, Data Health, HOFF_IN, Inventory, LOC_UTIL, LTA_QUEUE, LVLA_UTIL, Location Utilisation, Outbound TTA, PROD_PALLETS, Pallet Pattern, Pallets In Flow, Pallets Location, Pallets Movement, Planned PO RPM Breakdown, TTAT, TTAT_IN, TTAT_OUT, Truck Staging, USER_PROD |
| `{WO_WINDOW_DAYS}` | yes | Planned PO RPM Breakdown |
| `{ZONES_EXCL_BIN}` | yes | Pallets Location |
