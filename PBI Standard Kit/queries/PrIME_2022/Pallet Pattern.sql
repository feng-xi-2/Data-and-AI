-- Pallet Pattern - PrIME 2022 replica (schema dbo)
-- Source: PRIME ELS Hypercare KPI kit, sql/extracted/Pallet Pattern.m (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FG_PRTNUM_LIKE}, {WH_ID} - see ../TOKENS.md
-- Engine notes: Blue Yonder 2022 replica <SITE>_REPLICA: schema dbo, 5-framework zones (sto/pck/mov/wrk/cnt_zone_id on locmst), sto_zone table present.

        SELECT DISTINCT prtnum, ftpcod, untpal
        FROM (SELECT prtnum, ftpcod, untpal FROM dbo.prtftp_view WHERE wh_id = '{WH_ID}' AND defftp_flg = 1) AS footprint_md
        WHERE prtnum LIKE '{FG_PRTNUM_LIKE}'
    
