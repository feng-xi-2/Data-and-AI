-- Inventory - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/new/Inventory.sql (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {FG_PRTNUM_LIKE}, {LOC_TRAILER}, {PRTDSC_LOCALE}, {STOCK_AGE_CASE}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

-- Inventory (all sites: finished goods AND materials) - pallets in stock now by area, location class, WMS status and age band.
-- Age = days since the pallet's RECEIPT date (else FIFO date; dates after now = keying errors -> ignored, never a negative age) = time in this warehouse, site-local at Snapshot (the kit's aging rule,
-- as Pallets Location); a FIFO date is often the production date = product age, not dwell. Bands: config/stock_age_bands.csv.
-- Material = 'Finished goods' when the part number matches FG_PRTNUM_LIKE, else 'Materials'. Status = WMS description (dscmst invsts).
-- (Pallets Location is the BD materials view: it excludes finished goods, so it is nearly empty at a finished-goods DC.)
WITH n AS (
    SELECT DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) AS Snapshot
), p AS (
    SELECT iv.lodnum, iv.stoloc, iv.invsts, MIN(iv.prtnum) AS prtnum, SUM(CAST(iv.untqty AS DECIMAL(19, 3))) AS qty,
           MIN(COALESCE(CASE WHEN iv.rcvdte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN iv.rcvdte END,
                        CASE WHEN iv.fifdte <= DATEADD(HOUR, {UTC_Offset_h}, GETUTCDATE()) THEN iv.fifdte END)) AS since
    FROM prodwms.inventory_view AS iv
    WHERE iv.wh_id = '{WH_ID}'
    GROUP BY iv.lodnum, iv.stoloc, iv.invsts
), q AS (
    SELECT p.lodnum, p.invsts, p.prtnum, p.qty,
           COALESCE(lm.arecod, '(no area)') AS Area,
           CASE WHEN p.stoloc LIKE '{LOC_TRAILER}' THEN 'On trailer'
                WHEN lm.arecod LIKE 'RS%' OR lm.arecod LIKE 'RCV%' THEN 'Receiving'
                WHEN lm.arecod LIKE 'SHST%' THEN 'Shipping / staging'
                WHEN lm.arecod LIKE 'PE%' THEN 'Production line'
                ELSE 'Storage' END AS Loc_Class,
           DATEDIFF(DAY, p.since, n.Snapshot) AS age_days
    FROM p CROSS JOIN n
    LEFT JOIN prodwms.locmst AS lm ON lm.stoloc = p.stoloc AND lm.wh_id = '{WH_ID}'
    
), r AS (
    SELECT q.*, {{STOCK_AGE_CASE}} AS Age_Band FROM q
)
SELECT r.Area,
       r.Loc_Class                                                                            AS [Location Class],
       r.invsts                                                                               AS [Status Code],
       COALESCE(ds.lngdsc, r.invsts)                                                          AS Status,
       CASE WHEN r.prtnum LIKE '{FG_PRTNUM_LIKE}' THEN 'Finished goods' ELSE 'Materials' END AS Material,
       r.Age_Band,
       COUNT(*)                                                                               AS Pallets,
       SUM(r.qty)                                                                             AS Qty_BUoM,
       MAX(r.age_days)                                                                        AS Max_Age_Days,
       MAX(n.Snapshot)                                                                        AS Snapshot
FROM r CROSS JOIN n
LEFT JOIN prodwms.dscmst AS ds ON ds.colnam = 'invsts' AND ds.colval = r.invsts AND ds.locale_id = '{PRTDSC_LOCALE}'
GROUP BY r.Area, r.Loc_Class, r.invsts, COALESCE(ds.lngdsc, r.invsts), CASE WHEN r.prtnum LIKE '{FG_PRTNUM_LIKE}' THEN 'Finished goods' ELSE 'Materials' END, r.Age_Band
