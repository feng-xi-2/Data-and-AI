-- R04 equip -> PrIME 2022. RTCIS equipment class (1, 2, B, G, K, R, S, T, V, C) -> PrIME vehicle type (vehtyp).
-- Different code set (PrIME: FORK, CLMP, AGV_LB1 ...): column contract kept, values are PrIME's own. No parameters.
SELECT v.VEHTYP_ID AS equip,
       ISNULL(d.LNGDSC, v.VEHTYP_ID) AS equip_desc
FROM dbo.vehtyp v
LEFT JOIN dbo.dscmst d ON d.COLNAM = 'vehtyp_id' AND d.COLVAL = v.VEHTYP_ID AND d.LOCALE_ID = 'US_ENGLISH';
