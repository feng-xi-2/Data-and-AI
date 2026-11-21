-- R03 Direct LINE BEVO priorities -> PrIME 2022. Param: @wh_id.
-- RTCIS lindel (line delivery plan: line, process order, FP item, component, location, lot) ->
--   PrIME work-order lines wkodtl (component PRTNUM, PRCLOC line location, LOTNUM / SUP_LOTNUM) on open work orders.
--   lindel.PLNUMB (line number) -> wkohdr.PRDLIN; PRDORD -> WKONUM; ITMCOD -> wkohdr.PRTNUM (FP); SPCCOD -> wkodtl.PRTNUM.
--   LINSEQ -> wkodtl.WKOLIN [INFERRED]; LOCATN -> wkodtl.PRCLOC; CTLGRP -> wkodtl.LOTNUM; VNDCOD/VNDLOT -> SUP_LOTNUM split.
-- B/D counts: released (QASTAT 'RL' -> INVSTS 'U') packaging (ROH) pallets, excluding rework locations (RWZ).
-- E (PORECIPE/PRDQUE open demand, COMPLETE_FLAG 'A' active) -> wkohdr WKOSTS 'I' (in process); open qty = LINQTY - TOT_DLVQTY.
-- PrIME DE08 work-order data is DEV test data: compare structure, not volumes.
WITH rl AS (
    SELECT l.LODNUM, l.STOLOC AS locatn, d.PRTNUM AS itmcod, d.LOTNUM AS ctlgrp,
           NULLIF(LEFT(d.SUP_LOTNUM, 4), '') AS vndcod, NULLIF(SUBSTRING(d.SUP_LOTNUM, 5, 100), '') AS vndlot
    FROM dbo.invlod l JOIN dbo.invsub s ON s.LODNUM = l.LODNUM JOIN dbo.invdtl d ON d.SUBNUM = s.SUBNUM
    JOIN dbo.prtmst p ON p.PRTNUM = d.PRTNUM AND p.PRT_CLIENT_ID = d.PRT_CLIENT_ID AND p.WH_ID_TMPL = l.WH_ID
    WHERE l.WH_ID = @wh_id AND p.TYPCOD = 'ROH' AND l.STOLOC NOT LIKE '%RWZ%' AND d.INVSTS = 'U'
), B AS (SELECT COUNT(DISTINCT LODNUM) ULIDs, locatn, itmcod, vndlot, vndcod FROM rl GROUP BY locatn, itmcod, vndlot, vndcod),
   D AS (SELECT COUNT(DISTINCT LODNUM) ULIDs, vndcod, vndlot FROM rl GROUP BY vndcod, vndlot),
   A AS (
    SELECT h.PRDLIN AS PLNUMB, h.WKONUM AS PRDORD, h.PRTNUM AS ITMCOD, w.PRTNUM AS SPCCOD, w.WKOLIN AS LINSEQ,
           w.PRCLOC AS LOCATN, w.LOTNUM AS CTLGRP, NULLIF(LEFT(w.SUP_LOTNUM, 4), '') AS VNDCOD,
           NULLIF(SUBSTRING(w.SUP_LOTNUM, 5, 100), '') AS VNDLOT, h.WKOSTS, h.SCH_BEGDTE, h.SCH_ENDDTE,
           w.LINQTY - w.TOT_DLVQTY AS open_qty
    FROM dbo.wkohdr h
    JOIN dbo.wkodtl w ON w.WKONUM = h.WKONUM AND w.WKOREV = h.WKOREV AND w.WH_ID = h.WH_ID AND w.CLIENT_ID = h.CLIENT_ID
    JOIN dbo.prtmst p ON p.PRTNUM = w.PRTNUM AND p.PRT_CLIENT_ID = w.PRT_CLIENT_ID AND p.WH_ID_TMPL = w.WH_ID
    WHERE h.WH_ID = @wh_id AND h.WKOSTS IN ('P', 'I') AND p.TYPCOD = 'ROH' AND w.PRCLOC IS NOT NULL)
SELECT A.PLNUMB, A.PRDORD,
       CASE WHEN A.WKOSTS = 'I' AND A.open_qty > 0 THEN A.SCH_BEGDTE END AS ACTDAT,
       CASE WHEN A.WKOSTS = 'I' AND A.open_qty > 0 THEN A.SCH_ENDDTE END AS ENDDAT,
       A.ITMCOD, A.SPCCOD, A.LINSEQ, A.LOCATN, A.CTLGRP, A.VNDCOD, A.VNDLOT,
       B.ULIDs AS ULIDs_anhand_Ort, D.ULIDs AS ULIDs_anhand_Vendor_Lot,
       FORMAT(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime), 'dd.MM.yyyy HH:mm') AS Last_Update
FROM A
LEFT JOIN B ON A.SPCCOD = B.itmcod AND A.LOCATN = B.locatn AND A.VNDLOT = B.vndlot AND A.VNDCOD = B.vndcod
LEFT JOIN D ON A.VNDCOD = D.vndcod AND A.VNDLOT = D.vndlot
UNION
SELECT NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       FORMAT(MAX(TRNDTE), 'dd.MM.yyyy HH:mm')
FROM dbo.dlytrn WHERE WH_ID = @wh_id;
