-- Pallets Movement - site AKASHI (PrIME 2022, warehouse JP01) - rendered 2026-11-20 13:23 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT d.dlytrn_id,
       d.trndte                       AS txn_time,
       d.actcod,
       d.oprcod,
       d.frstol                       AS from_loc,
       d.fr_arecod                    AS from_area,
       CAST(lf.sto_zone_id AS NVARCHAR(20)) AS from_zone,
       d.tostol                       AS to_loc,
       d.to_arecod                    AS to_area,
       CAST(lt.sto_zone_id AS NVARCHAR(20)) AS to_zone,
       d.frinvs, d.toinvs,
       d.trnqty, d.uomcod,
       d.lodnum, d.to_lodnum, d.subnum, d.dtlnum,
       d.usr_id, d.devcod, d.reacod, d.movref, d.cmnt,
       DATEDIFF(MINUTE,
                LAG(d.trndte) OVER (ORDER BY d.trndte, d.dlytrn_id),
                d.trndte)             AS min_since_prev_txn
FROM (SELECT * FROM dbo.dlytrn WHERE wh_id = 'JP01') d
LEFT JOIN (SELECT * FROM dbo.locmst WHERE wh_id = 'JP01') lf ON lf.stoloc = d.frstol AND lf.wh_id = d.wh_id
LEFT JOIN (SELECT * FROM dbo.locmst WHERE wh_id = 'JP01') lt ON lt.stoloc = d.tostol AND lt.wh_id = d.wh_id
WHERE d.wh_id  = 'JP01' AND d.trndte >= DATEADD(DAY, -7, GETDATE()) AND d.trndte >= '1900-01-01' AND d.trndte < '9999-12-31'
 -- AND d.lodnum = '<LPN to trace>'
ORDER BY d.trndte, d.dlytrn_id;
