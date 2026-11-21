-- Pallet Pattern - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT prtnum, ftpcod, untpal
        FROM (SELECT prtnum, ftpcod, untpal FROM dbo.prtftp_view WHERE wh_id = 'BR01' AND defftp_flg = 1) AS footprint_md
        WHERE prtnum LIKE '[689]%'
