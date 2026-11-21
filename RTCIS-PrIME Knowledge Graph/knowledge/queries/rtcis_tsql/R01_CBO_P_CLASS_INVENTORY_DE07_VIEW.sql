-- R01 CBO_P_CLASS_INVENTORY_DE07_VIEW  (RTCIS, already T-SQL; only schema-qualified for the replica)
-- Connect: EUSKIRCHEN. No parameters.
SELECT        s1.LOCATN, s1.ITMCOD, s1.ITMGRP, s1.ULID20, s1.CASQTY, s1.QASTAT, s1.FIFODT, s1.CTLGRP, s1.ULPALL, s1.ZONCOD,
              getDate() AT TIME ZONE 'UTC' AT TIME ZONE 'Central Europe Standard Time' AS last_update,
              s1.BLDING, s1.MATTYP,
              (CASE WHEN s2.palflg = 'Y' THEN CONVERT(int, s2.u_height + 15) ELSE CONVERT(int, s2.u_height) END) AS calculated_pal_height,
              s2.UOM, cg.VNDCOD, cg.VNDLOT, { fn CONCAT(s1.ULPALL, s1.ITMCOD) } AS ULPAL_ITEM
FROM (SELECT DISTINCT iv.LOCATN, iv.ITMCOD, iv.ITMGRP, iv.ULID20, iv.CASQTY, iv.QASTAT, iv.FIFODT, iv.CTLGRP, iv.ULPALL, iv.ZONCOD,
             (CASE WHEN lo.PIKZON = 'X1' THEN CONVERT(Varchar(12), 'Halle 1') WHEN lo.PIKZON = 'X2' THEN CONVERT(Varchar(12), 'Halle 2')
                   WHEN lo.PIKZON = 'X3' THEN CONVERT(Varchar(12), 'Halle 3') WHEN lo.PIKZON = 'X4' THEN CONVERT(Varchar(12), 'Halle 4')
                   WHEN lo.PIKZON = 'X5' THEN CONVERT(Varchar(12), 'Halle 5') WHEN lo.PIKZON = 'XC' THEN CONVERT(Varchar(12), 'Modul')
                   ELSE CONVERT(Varchar(10), 'not defined') END) AS BLDING,
             (CASE WHEN substring(iv.itmgrp, 1, 1) = 'W' OR iv.itmgrp = 'PAPPWP' THEN CONVERT(Varchar(12), 'Wipes')
                   WHEN substring(iv.itmgrp, 1, 1) = 'R' THEN CONVERT(Varchar(12), 'Rawmaterial')
                   WHEN substring(iv.itmgrp, 1, 1) = 'P' THEN CONVERT(Varchar(12), 'Packmaterial')
                   ELSE CONVERT(Varchar(12), 'not defined') END) AS MATTYP
      FROM EUSKIRCHEN.live3.AGV_INVENTORY_VIEW AS iv
      INNER JOIN EUSKIRCHEN.live3.locatn AS lo ON iv.LOCATN = lo.LOCATN AND iv.SUBSIT = lo.SUBSIT
      WHERE (iv.ITMCLS = 'P') AND (iv.SUBSIT = '0')) AS s1
INNER JOIN (SELECT it.ITMCOD, iu.UOM, ic.CASLAY AS ITMCNF_CASLAY, ic.CASLAY * ic.LAYPUL AS ITMMST_QTY, ic.ULPALL, iu.U_HEIGHT, it.PALFLG
            FROM EUSKIRCHEN.live3.ITMMST AS it
            INNER JOIN EUSKIRCHEN.live3.ITEM_CONFIG AS ic ON it.ITMCOD = ic.ITMCOD
            INNER JOIN EUSKIRCHEN.live3.ITEM_UOM AS iu ON it.ITMCOD = iu.ITMCOD
            WHERE (iu.WHSFLG = 'Y') AND (it.ITMCLS = 'P') AND (it.PICFLG = 'Y')) AS s2
        ON s1.ITMCOD = s2.ITMCOD AND s1.ULPALL = s2.ULPALL
INNER JOIN EUSKIRCHEN.euskirchen.CBO_CTLGRP AS cg ON s1.CTLGRP = cg.CTLGRP AND s1.ITMCOD = cg.ITMCOD;
