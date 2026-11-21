-- Pallet Pattern - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/extracted/Pallet Pattern.m (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FG_PRTNUM_LIKE}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

        SELECT DISTINCT prtnum, ftpcod, untpal
        FROM (SELECT prtnum, ftpcod, untpal FROM prodwms.prtftp_view WHERE wh_id = '{WH_ID}' AND defftp_flg = 1) AS footprint_md
        WHERE prtnum LIKE '{FG_PRTNUM_LIKE}'
    
