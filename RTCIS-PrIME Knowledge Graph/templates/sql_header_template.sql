-- Rnn <query name> -> PrIME 2022.   Params: @wh_id (caller-bound), @locale (caller-bound), <original params by original name>
-- Every line below is one mapping decision. Tag each: MAPPED (measured, with rate) | [INFERRED] | [PARTIAL] | [ELIMINATED] | DEVIATION
--   <RTCIS table.column> -> <PrIME table.column / expression>   (<agreement on same physical objects>, <evidence file>)   MAPPED
--   <RTCIS column> -> no PrIME source (<columns / rows probed>) -> CAST(NULL AS <type>)                                   [ELIMINATED]
--   OBS6 DEVIATION (declared): <expert rule> replaced by <rule> because <measured numbers>
-- Grain: <how 1:n PrIME tables are collapsed - OUTER APPLY TOP 1 ... ORDER BY / SUM per key>   (OBS8)
-- Filters kept from the original: <list>; dropped: <list + tag>                                    (OBS7)
-- Units: quantity in <UOM>, <FLOOR to numeric(22,0) like RTCIS | exact>; dates site-local          (OBS6, receiving-uom)
SELECT
       <expr>                                   AS <ORIGINAL_COLUMN_1>,      -- same names, same order as the original (OBS5)
       CAST(NULL AS nvarchar(30))               AS <ORIGINAL_COLUMN_2>       -- [ELIMINATED] reason in field_notes.json
FROM dbo.<prime_table> t
JOIN dbo.prtmst p ON p.PRTNUM = t.PRTNUM AND p.PRT_CLIENT_ID = t.PRT_CLIENT_ID AND p.WH_ID_TMPL = t.WH_ID   -- WHT guard
OUTER APPLY (SELECT TOP 1 f.UOMCOD, f.UNTQTY FROM dbo.prtftp_dtl f
             WHERE f.PRTNUM = t.PRTNUM AND f.PRT_CLIENT_ID = t.PRT_CLIENT_ID AND f.WH_ID = t.WH_ID AND f.RCV_FLG = 1
             ORDER BY f.UOMLVL) r                                                                              -- FAN rule
WHERE t.WH_ID = @wh_id;
