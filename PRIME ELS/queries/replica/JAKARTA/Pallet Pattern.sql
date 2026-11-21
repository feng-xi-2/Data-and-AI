-- Pallet Pattern - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT prtnum, ftpcod, untpal
        FROM (SELECT prtnum, ftpcod, untpal FROM prodwms.prtftp_view WHERE wh_id = 'ID01' AND defftp_flg = 1) AS footprint_md
        WHERE prtnum LIKE '8%'
