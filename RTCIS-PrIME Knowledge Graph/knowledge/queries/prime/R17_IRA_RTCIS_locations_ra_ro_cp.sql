-- R17 IRA RTCIS locations RA/RO/CP -> PrIME 2022. Param: @wh_id.
-- RTCIS locatn arecod RA/RO/CP in subsit 0/1 -> PrIME storage locations, location type RSTO (measured: every RA/RO/CP
--   location found in DE08 is RSTO). Exclusions AL% / SILO% / CIMAT kept on STOLOC (CIMAT -> CIMATSTO at DE08).
--   zoncod 'D9' exclusion -> no PrIME zone equivalent [ELIMINATED].
-- subsit decode -> building B1 = DE07, B2 = DE08. blding (PIKZON/location prefix -> building code) -> '00' + area prefix
--   when numeric (area prefix = hall number, PIKZON X3->03, P7->07, 2P->12 ... measured), else the area code.
-- CYCDAT -> locmst.CNTDTE (last count date). POST/PRE_COUNT_OK -> NULL (PrIME has no pre/post count flags - IRA learnings).
-- serflg -> 'N' when USEFLG = 1 (in use) else 'Y' [INFERRED]; serflg_commnt -> LOKCOD [INFERRED].
-- actdat -> LSTDTE; itmcod (fixed item of the location) -> rplcfg pick-face item [INFERRED].
-- count_itmcls -> area-code infix 'FP' -> F, 'PM'/'RP' -> P, else the CL_LATEST_PRIME2022 rule: single stock class of the
--   location, else dominant stock class of the area by stocked locations (CL ranks pallets via inventory_view; invsum
--   is lighter and gives the same 98.8%). FERT -> F, ROH/HALB -> P. Where RTCIS is set: 18,386/18,618 (98.8%)
--   vs infix alone 95.3%. RTCIS leaves it empty on 25% of locations (no PrIME equivalent of 'not set') [INFERRED].
--   Scope RSTO = CL_LATEST_PRIME2022 STORAGE-not-ASRS on the RTCIS RA/RO/CP locations (25,580 both).
-- arecod RA/RO/CP -> PrIME area type (dscmst 'arecod|wh_id' SHORT_DSC): SUBP = CP (case pick), PAPA/LEDO = RA,
--   HOFF/MIXE = RO; PSTO/LOAP/FUPA hold both RA and RO, returned as the PrIME area type [PARTIAL - RA vs RO not derivable].
-- caslay (cases per layer) -> layer level UNTQTY / case level UNTQTY of that item; wm_unit -> receiving UOM.
WITH area_cls AS (
    SELECT ARECOD, TYPCOD FROM (
        SELECT b.ARECOD, c.TYPCOD,
               ROW_NUMBER() OVER (PARTITION BY b.ARECOD ORDER BY COUNT(DISTINCT a.STOLOC) DESC, c.TYPCOD) rn
        FROM dbo.invsum a
        JOIN dbo.locmst b ON b.STOLOC = a.STOLOC AND b.WH_ID = a.WH_ID
        JOIN dbo.prtmst c ON c.PRTNUM = a.PRTNUM AND c.PRT_CLIENT_ID = a.PRT_CLIENT_ID AND c.WH_ID_TMPL = a.WH_ID
        WHERE a.WH_ID = @wh_id
        GROUP BY b.ARECOD, c.TYPCOD) z
    WHERE rn = 1),
loc_cls AS (
    SELECT y.STOLOC, CASE WHEN MIN(x.TYPCOD) = MAX(x.TYPCOD) THEN MAX(x.TYPCOD) END AS TYPCOD
    FROM dbo.invsum y
    JOIN dbo.prtmst x ON x.PRTNUM = y.PRTNUM AND x.PRT_CLIENT_ID = y.PRT_CLIENT_ID AND x.WH_ID_TMPL = y.WH_ID
    WHERE y.WH_ID = @wh_id
    GROUP BY y.STOLOC)
SELECT CASE a.BLDG_ID WHEN 'B1' THEN 'DE07' WHEN 'B2' THEN 'DE08' ELSE a.BLDG_ID END AS subsit,
       CASE WHEN m.STOLOC LIKE 'HOF%' THEN 'AUSSENBEREICH'
            WHEN LEFT(m.ARECOD, 2) LIKE '[0-9][0-9]' THEN '00' + LEFT(m.ARECOD, 2)
            ELSE m.ARECOD END AS blding,
       m.STOLOC AS locatn,
       COALESCE(CASE SUBSTRING(m.ARECOD, 3, 2) WHEN 'FP' THEN 'F' WHEN 'PM' THEN 'P' WHEN 'RP' THEN 'P' END,
                CASE ISNULL(ls.TYPCOD, ac.TYPCOD) WHEN 'FERT' THEN 'F' WHEN 'ROH' THEN 'P' WHEN 'HALB' THEN 'P' END) AS count_itmcls,
       m.CNTDTE AS CYCDAT,
       ROUND(DATEDIFF(second, m.CNTDTE, GETDATE()) / 86400.0, 0) AS last_count_durration_days,
       CAST(NULL AS varchar(1)) AS POST_COUNT_OK, CAST(NULL AS varchar(1)) AS PRE_COUNT_OK,
       CASE WHEN m.USEFLG = 1 THEN 'N' ELSE 'Y' END AS serflg,
       m.LOKCOD AS serflg_commnt,
       FORMAT(m.LSTDTE, 'dd.MM.yyyy HH:mm') AS actdat,
       rp.PRTNUM AS itmcod,
       CASE ty.SHORT_DSC WHEN 'SUBP' THEN 'CP' WHEN 'PAPA' THEN 'RA' WHEN 'LEDO' THEN 'RA' WHEN 'HOFF' THEN 'RO' WHEN 'MIXE' THEN 'RO'
            ELSE ty.SHORT_DSC END AS arecod,
       CAST(CAST(CAST(ly.UNTQTY AS decimal(19,3)) / NULLIF(cs.UNTQTY, 0) AS int) AS varchar(20)) AS caslay,
       rc.UOMCOD AS wm_unit,
       FORMAT(CAST(SYSDATETIMEOFFSET() AT TIME ZONE 'Central Europe Standard Time' AS datetime), 'dd.MM.yyyy HH:mm') AS last_update
FROM dbo.locmst m
JOIN dbo.aremst a ON a.ARECOD = m.ARECOD AND a.WH_ID = m.WH_ID
JOIN dbo.loc_typ t ON t.LOC_TYP_ID = m.LOC_TYP_ID
LEFT JOIN dbo.dscmst ty ON ty.COLNAM = 'arecod|wh_id' AND ty.COLVAL = m.ARECOD + '|' + m.WH_ID AND ty.LOCALE_ID = 'US_ENGLISH'
-- HASH join hints: without them DE08 re-aggregates the class sets per location (>5 min vs 16 s).
LEFT HASH JOIN area_cls ac ON ac.ARECOD = m.ARECOD
LEFT HASH JOIN loc_cls ls ON ls.STOLOC = m.STOLOC
OUTER APPLY (SELECT TOP 1 r.PRTNUM, r.PRT_CLIENT_ID FROM dbo.rplcfg r WHERE r.STOLOC = m.STOLOC AND r.WH_ID = m.WH_ID ORDER BY r.PRTNUM) rp
LEFT JOIN dbo.prtmst p ON p.PRTNUM = rp.PRTNUM AND p.PRT_CLIENT_ID = rp.PRT_CLIENT_ID AND p.WH_ID_TMPL = m.WH_ID
OUTER APPLY (SELECT TOP 1 f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = rp.PRTNUM AND f.PRT_CLIENT_ID = rp.PRT_CLIENT_ID
             AND f.WH_ID = m.WH_ID AND f.LAYER_FLG = 1 ORDER BY f.UOMLVL) ly
OUTER APPLY (SELECT TOP 1 f.UNTQTY FROM dbo.prtftp_dtl f WHERE f.PRTNUM = rp.PRTNUM AND f.PRT_CLIENT_ID = rp.PRT_CLIENT_ID
             AND f.WH_ID = m.WH_ID AND f.CAS_FLG = 1 ORDER BY f.UOMLVL) cs
OUTER APPLY (SELECT TOP 1 f.UOMCOD FROM dbo.prtftp_dtl f WHERE f.PRTNUM = rp.PRTNUM AND f.PRT_CLIENT_ID = rp.PRT_CLIENT_ID
             AND f.WH_ID = m.WH_ID AND f.RCV_FLG = 1 ORDER BY f.UOMLVL) rc
WHERE m.WH_ID = @wh_id AND t.LOC_TYP = 'RSTO'
  AND m.STOLOC NOT LIKE 'AL%' AND m.STOLOC NOT LIKE 'SILO%' AND m.STOLOC NOT LIKE 'CIMAT%'
ORDER BY subsit, m.STOLOC, m.ARECOD;
