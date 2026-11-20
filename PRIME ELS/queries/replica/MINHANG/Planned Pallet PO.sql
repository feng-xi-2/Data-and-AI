-- Planned Pallet PO - site MINHANG (PrIME 2022, warehouse BR01) - rendered 2026-11-20 13:21 by tools/compare_replica_pbi.py
-- = the query the Power BI model sends to this site's replica (tokens from config/site_config.csv)
SELECT
            w.wkonum        AS work_order,
            w.prdlin        AS product_line,
            d.lngdsc        AS status,
            w.sch_begdte    AS planned_start,
            w.sch_enddte    AS planned_end,
            DATEDIFF(HOUR, w.sch_begdte, w.sch_enddte) AS duration_hours,
            w.prtnum,
            prtdsc.lngdsc   AS description,
            w.wkoqty        AS planned_cases,
            p.untpal        AS cases_per_pallet,
            p.ftpcod,
            CAST(CAST(w.wkoqty AS DECIMAL(18,2)) / NULLIF(p.untpal, 0) AS DECIMAL(18,2)) AS planned_pallets,
            CAST(
                (CAST(w.wkoqty AS DECIMAL(18,2)) / NULLIF(p.untpal, 0))
                / NULLIF(DATEDIFF(HOUR, w.sch_begdte, w.sch_enddte), 0)
            AS DECIMAL(18,2)) AS planned_pallets_per_hour
        FROM (SELECT * FROM dbo.wkohdr WHERE wh_id = 'BR01') w
        JOIN dbo.dscmst d
            ON d.colnam = 'wkosts'
           AND d.locale_id = 'US_ENGLISH'
           AND w.wkosts = d.colval
        LEFT JOIN (
            SELECT DISTINCT prtnum, ftpcod, untpal
            FROM (SELECT prtnum, ftpcod, untpal FROM dbo.prtftp_view WHERE wh_id = 'BR01' AND defftp_flg = 1) AS footprint_md
            WHERE prtnum LIKE '[689]%'
        ) p
            ON p.prtnum = w.prtnum
        LEFT JOIN dbo.prtdsc
            ON prtdsc.colval LIKE CONCAT(w.prtnum, '%BR01%')
           AND prtdsc.locale_id = 'US_ENGLISH'
        WHERE w.prtnum LIKE '[689]%'
        AND w.sch_enddte >= DATEADD(DAY, -30, DATEADD(HOUR, 8, GETUTCDATE()))
                  AND w.sch_begdte <  DATEADD(DAY, 30, DATEADD(HOUR, 8, GETUTCDATE()))
                ORDER BY w.sch_begdte;
