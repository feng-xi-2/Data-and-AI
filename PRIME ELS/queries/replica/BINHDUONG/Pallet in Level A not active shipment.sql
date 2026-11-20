-- Pallet in Level A not active shipment - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:18 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT i.newdte,
            i.prtnum,
            i.stoloc,
            SUM(i.untqty - i.comqty) AS Available_qty
        FROM (SELECT * FROM dbo.invsum WHERE wh_id = 'VN07') i
        WHERE i.stoloc LIKE 'F0%A'
          AND i.comqty < i.untqty
                  AND EXISTS (SELECT 1 FROM (SELECT * FROM dbo.locmst WHERE wh_id = 'VN07') AS l WHERE l.wh_id = i.wh_id AND l.stoloc = i.stoloc AND l.useflg = 1 AND l.stoflg = 1 AND l.maxqvl > 0)
          AND NOT EXISTS (
              SELECT 1
              FROM (SELECT * FROM dbo.shipment_line WHERE wh_id = 'VN07') sl,
                   (SELECT * FROM dbo.ord_line WHERE wh_id = 'VN07') ol,
                   (SELECT * FROM dbo.shipment WHERE wh_id = 'VN07') s
              WHERE ol.prtnum = i.prtnum
                AND sl.ordnum = ol.ordnum
                AND sl.ordlin = ol.ordlin
                AND sl.ordsln = ol.ordsln
                AND sl.wh_id  = ol.wh_id
                AND sl.linsts = 'P'
                AND sl.linsts NOT IN ('B', 'C')
                AND sl.ship_id = s.ship_id
                AND s.shpsts NOT IN ('B', 'C', 'D')
          )
        AND i.newdte > '2026-07-26 00:00:00'
        GROUP BY i.prtnum, i.stoloc, i.newdte
        ORDER BY newdte DESC;
