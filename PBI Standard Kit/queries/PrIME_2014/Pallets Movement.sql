-- Pallets Movement - PrIME 2014 replica (schema prodwms)
-- Source: PRIME ELS Hypercare KPI kit, sql/extracted/Pallets Movement.m (validated on the replicas with tools/validate_sql.py)
-- Replace the site tokens before running: {INC_FROM}, {INC_TO}, {MOVEMENT_DAYS}, {WH_ID} - see ../TOKENS.md
-- Engine notes: RedPrairie/JDA 2014 replica <SITE>: schema prodwms, no sto_zone table and no locmst.sto_zone_id - storage zoning is by area (arecod); footprint_md view absent -> prtftp_view. No loc_typ table: location type falls back to area prefixes (PE*=line, RS*/RCV*=receiving, SHST*=shipping).

SELECT d.dlytrn_id,
       d.trndte                       AS txn_time,
       d.actcod,
       d.oprcod,
       d.frstol                       AS from_loc,
       d.fr_arecod                    AS from_area,
       CAST(lf.arecod AS NVARCHAR(20)) AS from_zone,
       d.tostol                       AS to_loc,
       d.to_arecod                    AS to_area,
       CAST(lt.arecod AS NVARCHAR(20)) AS to_zone,
       d.frinvs, d.toinvs,
       d.trnqty, d.uomcod,
       d.lodnum, d.to_lodnum, d.subnum, d.dtlnum,
       d.usr_id, d.devcod, d.reacod, d.movref, d.cmnt,
       DATEDIFF(MINUTE,
                LAG(d.trndte) OVER (ORDER BY d.trndte, d.dlytrn_id),
                d.trndte)             AS min_since_prev_txn
FROM (SELECT * FROM prodwms.dlytrn WHERE wh_id = '{WH_ID}') d
LEFT JOIN (SELECT * FROM prodwms.locmst WHERE wh_id = '{WH_ID}') lf ON lf.stoloc = d.frstol AND lf.wh_id = d.wh_id
LEFT JOIN (SELECT * FROM prodwms.locmst WHERE wh_id = '{WH_ID}') lt ON lt.stoloc = d.tostol AND lt.wh_id = d.wh_id
WHERE d.wh_id  = '{WH_ID}' AND d.trndte >= DATEADD(DAY, -{MOVEMENT_DAYS}, GETDATE()) AND d.trndte >= {INC_FROM} AND d.trndte < {INC_TO}
 -- AND d.lodnum = '<LPN to trace>'
ORDER BY d.trndte, d.dlytrn_id;
