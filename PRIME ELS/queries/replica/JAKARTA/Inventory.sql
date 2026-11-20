-- Inventory - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
-- Inventory (all sites: finished goods AND materials) - pallets in stock now by area, location class, WMS status and age band.
-- Age = days since the pallet's RECEIPT date (else FIFO date; dates after now = keying errors -> ignored, never a negative age) = time in this warehouse, site-local at Snapshot (the kit's aging rule,
-- as Pallets Location); a FIFO date is often the production date = product age, not dwell. Bands: config/stock_age_bands.csv.
-- Material = 'Finished goods' when the part number matches FG_PRTNUM_LIKE, else 'Materials'. Status = WMS description (dscmst invsts).
-- (Pallets Location is the BD materials view: it excludes finished goods, so it is nearly empty at a finished-goods DC.)
WITH n AS (
    SELECT DATEADD(HOUR, 7, GETUTCDATE()) AS Snapshot
), p AS (
    SELECT iv.lodnum, iv.stoloc, iv.invsts, MIN(iv.prtnum) AS prtnum, SUM(CAST(iv.untqty AS DECIMAL(19, 3))) AS qty,
           MIN(COALESCE(CASE WHEN iv.rcvdte <= DATEADD(HOUR, 7, GETUTCDATE()) THEN iv.rcvdte END,
                        CASE WHEN iv.fifdte <= DATEADD(HOUR, 7, GETUTCDATE()) THEN iv.fifdte END)) AS since
    FROM (SELECT * FROM prodwms.inventory_view WHERE wh_id = 'ID01') AS iv
    WHERE iv.wh_id = 'ID01'
    GROUP BY iv.lodnum, iv.stoloc, iv.invsts
), q AS (
    SELECT p.lodnum, p.invsts, p.prtnum, p.qty,
           COALESCE(lm.arecod, '(no area)') AS Area,
           CASE WHEN p.stoloc LIKE 'TRL%' THEN 'On trailer'
                WHEN lm.arecod LIKE 'RS%' OR lm.arecod LIKE 'RCV%' THEN 'Receiving'
                WHEN lm.arecod LIKE 'SHST%' THEN 'Shipping / staging'
                WHEN lm.arecod LIKE 'PE%' THEN 'Production line'
                ELSE 'Storage' END AS Loc_Class,
           DATEDIFF(DAY, p.since, n.Snapshot) AS age_days
    FROM p CROSS JOIN n
    LEFT JOIN (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01') AS lm ON lm.stoloc = p.stoloc AND lm.wh_id = 'ID01'
    
), r AS (
    SELECT q.*, CASE WHEN q.age_days IS NULL THEN 'Unknown' WHEN q.age_days < 1 THEN '0-1 d' WHEN q.age_days < 3 THEN '1-3 d' WHEN q.age_days < 7 THEN '3-7 d' WHEN q.age_days < 30 THEN '7-30 d' WHEN q.age_days < 90 THEN '30-90 d' WHEN q.age_days < 100000 THEN '> 90 d' ELSE '> 90 d' END AS Age_Band FROM q
)
SELECT r.Area,
       r.Loc_Class                                                                            AS [Location Class],
       r.invsts                                                                               AS [Status Code],
       COALESCE(ds.lngdsc, r.invsts)                                                          AS Status,
       CASE WHEN r.prtnum LIKE '8%' THEN 'Finished goods' ELSE 'Materials' END AS Material,
       r.Age_Band,
       COUNT(*)                                                                               AS Pallets,
       SUM(r.qty)                                                                             AS Qty_BUoM,
       MAX(r.age_days)                                                                        AS Max_Age_Days,
       MAX(n.Snapshot)                                                                        AS Snapshot
FROM r CROSS JOIN n
LEFT JOIN prodwms.dscmst AS ds ON ds.colnam = 'invsts' AND ds.colval = r.invsts AND ds.locale_id = 'US_ENGLISH'
GROUP BY r.Area, r.Loc_Class, r.invsts, COALESCE(ds.lngdsc, r.invsts), CASE WHEN r.prtnum LIKE '8%' THEN 'Finished goods' ELSE 'Materials' END, r.Age_Band
