-- Pallet cleaned up from bin A - site JAKARTA (PrIME 2014, warehouse ID01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT DISTINCT a.prtnum,a.lodnum,
                a.frstol as A_LOCATION,
                b.tostol as FINAL_LOCATION,
                b.trndte as MOVE_DATE
           from (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') a,
                (SELECT * FROM prodwms.dlytrn WHERE wh_id = 'ID01') b
          where a.lodnum = b.lodnum
            and a.frstol like 'C%A'
            and a.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and a.trndte >= '2026-10-20 00:00:00'
            and b.fr_arecod LIKE 'RDTS%'
            and b.actcod in ('FL_XFR', 'FL_XFR_PTWY')
            and b.trndte >= a.trndte AND b.trndte >= '1900-01-01' AND b.trndte < '9999-12-31'
            and b.tostol not like 'C%A'
            and b.tostol in (select stoloc
                               from (SELECT * FROM prodwms.locmst WHERE wh_id = 'ID01') AS locmst
                              where arecod is not null
                                and CAST(arecod AS NVARCHAR(40)) not in ('~NA~'))
        order by move_date desc;
