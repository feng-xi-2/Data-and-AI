-- ACTIVE_USERS - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/reference/ACTIVE_USERS.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FROM}, {TO}, {USR_EXCLUDE}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- ACTIVE USERS: RF users with at least one pallet transaction in the window (system / automatic activity codes and
-- USR_EXCLUDE users excluded - same exclusions as the KPI definition on the User Productivity page).
SELECT COUNT(DISTINCT d.usr_id) AS v
FROM prodwms.dlytrn d
WHERE d.wh_id = '{WH_ID}' AND d.trndte >= '{FROM}' AND d.trndte < '{TO}'
  AND d.usr_id IS NOT NULL AND d.usr_id NOT IN ({USR_EXCLUDE}) AND d.lodnum IS NOT NULL
  AND d.actcod NOT IN ('LOCSTSCHG','ATELOCSETAUTO','ATELOCCLRAUTO','INVSTSCHG','LOTDATECHANGED','LOCOVRRID','WRKSUSP','ENG_EXEMP_CHG')
