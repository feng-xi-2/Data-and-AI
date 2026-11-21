-- SAP Production (CDL) - finished-goods goods receipts against production orders (MATDOC 101, reversals 102) per plant / posting day / material, last {ACT_DAYS} days
-- Pallets = quantity / MARM factor of the site's pallet unit (Cfg_Site.SAP_PALLET_UOM); a material without that unit counts 1 pallet per GR line
-- (HU-managed plants post one GR per pallet - validated on Binh Duong 9772: GR lines 1,082 / 568 / 45 / 305 vs WMS produced pallets 1,090 / 568 / 45 / 304).
WITH gr AS (
    SELECT m.werks AS Plant,
           CAST(CAST(m.matnr AS INT) AS STRING) AS MatNr,
           CAST(CONCAT(LEFT(m.budat, 4), '-', SUBSTR(m.budat, 5, 2), '-', RIGHT(m.budat, 2)) AS DATE) AS Posting_Date,
           m.meins AS BUoM,
           CASE WHEN m.bwart = '102' THEN -1 ELSE 1 END AS Sign,
           CAST(m.menge AS DOUBLE) AS Qty
    FROM cdl_oss_prod.silver_sap_a6p.matdoc AS m
    JOIN cdl_oss_prod.silver_sap_a6p.mara AS d ON CAST(d.matnr AS INT) = CAST(m.matnr AS INT) AND d.mtart = 'FERT'
    WHERE m.werks = '{SAP_Plant}' AND m.bwart IN ('101', '102') AND COALESCE(m.aufnr, '') <> ''
      AND m.sap_chng_type_code <> 'D'
      AND m.budat >= DATE_FORMAT(DATE_ADD(CURRENT_DATE(), -{ACT_DAYS}), 'yyyyMMdd')
),
pal AS (
    SELECT CAST(matnr AS INT) AS MatNrKey,
           MAX(CAST(umrez AS DOUBLE)) / NULLIF(MAX(CAST(umren AS DOUBLE)), 0) AS Factor
    FROM cdl_oss_prod.silver_sap_a6p.marm
    WHERE sap_chng_type_code <> 'D' AND meinh = '{SAP_PALLET_UOM}'
      AND TRY_CAST(umrez AS DOUBLE) <> 0 AND TRY_CAST(umren AS DOUBLE) <> 0
      AND CAST(matnr AS INT) IN (SELECT DISTINCT CAST(MatNr AS INT) FROM gr)
    GROUP BY CAST(matnr AS INT)
),
txt AS (
    SELECT CAST(matnr AS INT) AS MatNrKey, MAX(maktx) AS MatDesc
    FROM cdl_oss_prod.silver_sap_a6p.makt
    WHERE spras = 'E' AND CAST(matnr AS INT) IN (SELECT DISTINCT CAST(MatNr AS INT) FROM gr)
    GROUP BY CAST(matnr AS INT)
)
SELECT g.Plant,
       g.Posting_Date,
       g.MatNr,
       MAX(t.MatDesc)                                         AS MatDesc,
       g.BUoM,
       SUM(g.Sign)                                            AS GR_Lines,
       SUM(g.Sign * g.Qty)                                    AS Qty_BUoM,
       ROUND(SUM(g.Sign * COALESCE(g.Qty / p.Factor, 1)), 2)  AS Pallets,
       MAX(CASE WHEN p.Factor IS NULL THEN 'GR line = 1 pallet' ELSE 'MARM {SAP_PALLET_UOM}' END) AS Pallet_Basis
FROM gr AS g
LEFT JOIN pal AS p ON p.MatNrKey = CAST(g.MatNr AS INT)
LEFT JOIN txt AS t ON t.MatNrKey = CAST(g.MatNr AS INT)
GROUP BY g.Plant, g.Posting_Date, g.MatNr, g.BUoM
