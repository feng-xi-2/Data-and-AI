-- Pallet from LTA to short/tall location - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:18 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT 
            i.stoloc,
            i.lodnum,
            i.prtnum,
            i.ftpcod,
            p.hgt AS pallet_height,
            CASE WHEN p.hgt > 150 THEN 'OVER_150'
                 ELSE '150_OR_LESS'
            END AS height_category
        FROM (SELECT * FROM dbo.inventory_view WHERE wh_id = 'VN07') i,
             (SELECT * FROM dbo.prtftp_dtl WHERE wh_id = 'VN07') p
        WHERE p.prtnum = i.prtnum
          AND i.stoloc LIKE 'LT%'
          AND i.ftpcod = p.ftpcod
          AND p.wh_id = 'VN07'
          AND p.uomcod = 'PL'
          AND i.lstdte >= '2026-07-26 00:00:00';
