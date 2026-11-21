-- Pallet cleaned up from bin A - site BINHDUONG (PrIME 2022, warehouse VN07) - rendered 2026-11-20 13:18 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT a.prtnum,a.lodnum,
                a.frstol as A_LOCATION,
                b.tostol as FINAL_LOCATION,
                b.trndte as MOVE_DATE
           from (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') a,
                (SELECT * FROM dbo.dlytrn WHERE wh_id = 'VN07') b
          where a.lodnum = b.lodnum
            and a.frstol like 'F0%A'
            and a.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and a.trndte >= '2026-07-26 00:00:00'
            and b.fr_arecod LIKE 'RDTS'
            and b.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and b.trndte >= a.trndte AND b.trndte >= '1900-01-01' AND b.trndte < '9999-12-31'
            and b.tostol not like 'F0%A'
            and b.tostol in (select stoloc
                               from (SELECT * FROM dbo.locmst WHERE wh_id = 'VN07') AS locmst
                              where sto_zone_id is not null
                                and CAST(sto_zone_id AS NVARCHAR(40)) not in ('10148','10153','10040'))
        order by move_date desc;
