-- R11 IMP line return history FROM RTCIS (live). Same as R10; window literal 33 days up to now, as the original.
SELECT CASE sd.LOCATN WHEN 'SILOB' THEN 'ULINA4' WHEN 'SILOA' THEN 'ULINA3' ELSE sd.LOCATN END AS LINE,
       FORMAT(st.SYSDAT, 'yyyy-MM-dd HH:mm:ss') AS RETURN_DATE,
       sd.ITMCOD, LEFT(it.ITMDSC, 15) AS DESCRIPTION, sd.CTLGRP, LEFT(ct.VNDCOD, 4) AS VENDOR, ct.VNDLOT AS VENDOR_LOT,
       st.TRNQTY AS QTY, iu.UOM AS WM_UNIT, SUBSTRING(st.PRDORD, 4, 9) AS PROCESS_ORDER, sd.ULID AS ULID,
       CONCAT(sd.ULID, FORMAT(st.SYSDAT, 'yyyy.MM.dd HH:mm:ss')) AS ID_NR
FROM [EUSKIRCHEN_simp].live3.sysdtl sd
JOIN [EUSKIRCHEN_simp].live3.systrn st ON st.TRNSEQ = sd.TRNSEQ
JOIN [EUSKIRCHEN_simp].live3.itmmst it ON sd.ITMCLS = it.ITMCLS AND sd.ITMCOD = it.ITMCOD
JOIN [EUSKIRCHEN_simp].live3.item_uom iu ON it.ITMCOD = iu.ITMCOD
JOIN [EUSKIRCHEN_simp].live3.ctlgrp ct ON sd.ITMCOD = ct.ITMCOD AND sd.ITMCLS = ct.ITMCLS AND sd.CTLGRP = ct.CTLGRP
WHERE sd.ITMCLS = 'P' AND sd.SUBSIT = '0' AND iu.WHSFLG = 'Y'
  AND sd.LOCATN LIKE 'ULIN%' AND st.TRNTYP = 'MANLID'
  AND st.SYSDAT > DATEADD(day, -33, GETDATE()) AND st.SYSDAT <= GETDATE();
