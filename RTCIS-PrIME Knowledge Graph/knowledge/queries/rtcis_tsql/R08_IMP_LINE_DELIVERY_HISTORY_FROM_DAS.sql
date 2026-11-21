-- R08 IMP line delivery history FROM DAS (RTCIS). T-SQL transliteration of the SYS_get_DAS Oracle text.
-- DAS archive tables DASLIV1.SYSTRN/SYSDTL_RTCIS_CUR -> replica live3.systrn/sysdtl (~40 days kept). Window: last 3 days.
-- Part 1: DEPSUL/LINUSE packaging moves to ULIN%. Part 2: CASXFR case transfers to a ULIN% line (T detail = line, F detail = item).
-- Window literal 3 days, exactly as the original (sysdate - 3); see R09 for the 120-minute RTCIS variant.
WITH p1 AS (
    SELECT CASE sd.LOCATN WHEN 'SILOB' THEN 'ULINA4' WHEN 'SILOA' THEN 'ULINA3' ELSE sd.LOCATN END AS LOCATN,
           st.SYSDAT, sd.ITMCOD, LEFT(it.ITMDSC, 15) AS ITMDSC, sd.CTLGRP, LEFT(ct.VNDCOD, 4) AS VNDCOD, ct.VNDLOT,
           st.TRNQTY, iu.UOM, SUBSTRING(st.PRDORD, 4, 9) AS PRDORD, LEFT(sd.ULID, 20) AS ULID
    FROM [EUSKIRCHEN_simp].live3.sysdtl sd
    JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
    JOIN [EUSKIRCHEN_simp].live3.itmmst it ON sd.ITMCLS = it.ITMCLS AND sd.ITMCOD = it.ITMCOD
    JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.ITMCOD = iu.ITMCOD
    JOIN [EUSKIRCHEN_simp].live3.ctlgrp ct ON sd.ITMCOD = ct.ITMCOD AND sd.ITMCLS = ct.ITMCLS AND sd.CTLGRP = ct.CTLGRP
    WHERE sd.ITMCLS = 'P' AND sd.SUBSIT = '0' AND iu.WHSFLG = 'Y'
      AND sd.LOCATN LIKE 'ULIN%' AND st.TRNTYP IN ('DEPSUL', 'LINUSE')
      AND st.SYSDAT > DATEADD(day, -3, GETDATE())
), sq1 AS (
    SELECT CASE sd.LOCATN WHEN 'SILOB' THEN 'ULINA4' WHEN 'SILOA' THEN 'ULINA3' ELSE sd.LOCATN END AS LOCATN, st.TRNSEQ
    FROM [EUSKIRCHEN_simp].live3.sysdtl sd JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
    WHERE sd.LOCATN LIKE 'ULIN%' AND sd.DTLTYP = 'T' AND st.PRDORD IS NOT NULL AND sd.SUBSIT = '0'
      AND st.SYSDAT > DATEADD(day, -3, GETDATE())
), p2 AS (
    SELECT sq1.LOCATN, st.SYSDAT, sd.ITMCOD, LEFT(it.ITMDSC, 15) AS ITMDSC, sd.CTLGRP, LEFT(ct.VNDCOD, 4) AS VNDCOD, ct.VNDLOT,
           st.TRNQTY, iu.UOM, SUBSTRING(st.PRDORD, 4, 9) AS PRDORD, LEFT(sd.ULID, 20) AS ULID
    FROM [EUSKIRCHEN_simp].live3.sysdtl sd
    JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
    JOIN sq1 ON sq1.TRNSEQ = st.TRNSEQ
    JOIN [EUSKIRCHEN_simp].live3.itmmst it ON sd.ITMCLS = it.ITMCLS AND sd.ITMCOD = it.ITMCOD
    JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.ITMCOD = iu.ITMCOD
    JOIN [EUSKIRCHEN_simp].live3.ctlgrp ct ON sd.ITMCOD = ct.ITMCOD AND sd.ITMCLS = ct.ITMCLS AND sd.CTLGRP = ct.CTLGRP
    WHERE sd.DTLTYP = 'F' AND sd.SUBSIT = '0' AND st.TRNTYP = 'CASXFR' AND st.PRDORD IS NOT NULL AND iu.WHSFLG = 'Y'
      AND st.SYSDAT > DATEADD(day, -3, GETDATE())
)
SELECT LOCATN AS LINE, FORMAT(SYSDAT, 'yyyy-MM-dd HH:mm:ss') AS DELIVERY_DATE, ITMCOD, ITMDSC AS DESCRIPTION, CTLGRP,
       VNDCOD AS VENDOR, VNDLOT AS VENDOR_LOT, TRNQTY AS QTY, UOM AS WM_UNIT, PRDORD AS PROCESS_ORDER, ULID,
       CONCAT(ULID, FORMAT(SYSDAT, 'yyyy.MM.dd HH:mm:ss')) AS ID_NR
FROM p1
UNION
SELECT LOCATN, FORMAT(SYSDAT, 'yyyy-MM-dd HH:mm:ss'), ITMCOD, ITMDSC, CTLGRP, VNDCOD, VNDLOT, TRNQTY, UOM, PRDORD, ULID,
       CONCAT(ULID, FORMAT(SYSDAT, 'yyyy.MM.dd HH:mm:ss'))
FROM p2;
