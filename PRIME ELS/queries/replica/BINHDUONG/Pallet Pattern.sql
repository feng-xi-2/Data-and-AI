-- Pallet Pattern - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:18 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT prtnum, ftpcod, untpal
        FROM binhduong_replica.footprint_md
        WHERE prtnum LIKE '8%'
