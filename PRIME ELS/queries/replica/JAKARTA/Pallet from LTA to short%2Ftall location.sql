-- Pallet from LTA to short/tall location - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
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
        FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') i,
             (SELECT * FROM prodwms.prtftp_dtl WHERE wh_id = 'ID01') p
        WHERE p.prtnum = i.prtnum
          AND i.stoloc LIKE '~NA~'
          AND i.ftpcod = p.ftpcod
          AND p.wh_id = 'ID01'
          AND p.uomcod = 'PL'
          AND i.lstdte >= '2026-10-20 00:00:00';
