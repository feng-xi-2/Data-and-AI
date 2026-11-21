# Model / report best-practice check

Run by `py tools/build_pbip.py` on every build (rules: Microsoft skills-for-fabric modeling guidelines, Tabular Editor BPA).

**CRITICAL: 0** (build fails)  |  RECOMMENDED: 0  |  broken filters removed at build: 1

## Broken filters removed (field not in the model)

- 1924d04526133720a3b3: {"Measure": {"Expression": {"SourceRef": {"Entity": "SecurityRole"}}, "Property": "IsHRUser"}}

## Standard format applied to 35 numeric measure(s) without one

- [Sort_Helper] -> #,0.##
- [Outbound_Level A %] -> 0.0%
- [Input PPH Target] -> #,0.##
- [Input PPH Warn] -> #,0.##
- [Input PPH Crit] -> #,0.##
- [Thr PPH Target] -> #,0.##
- [Thr PPH Warn] -> #,0.##
- [Thr PPH Crit] -> #,0.##
- [Input TTAT_IN Target] -> #,0.##
- [Input TTAT_IN Warn] -> #,0.##
- [Input TTAT_IN Crit] -> #,0.##
- [Thr TTAT_IN Target] -> #,0.##
- [Thr TTAT_IN Warn] -> #,0.##
- [Thr TTAT_IN Crit] -> #,0.##
- [Input TTAT_OUT Target] -> #,0.##
- [Input TTAT_OUT Warn] -> #,0.##
- [Input TTAT_OUT Crit] -> #,0.##
- [Thr TTAT_OUT Target] -> #,0.##
- [Thr TTAT_OUT Warn] -> #,0.##
- [Thr TTAT_OUT Crit] -> #,0.##
- [Input LOC_UTIL Target] -> #,0.##
- [Input LOC_UTIL Warn] -> #,0.##
- [Input LOC_UTIL Crit] -> #,0.##
- [Thr LOC_UTIL Target] -> #,0.##
- [Thr LOC_UTIL Warn] -> #,0.##
- [Thr LOC_UTIL Crit] -> #,0.##
- [Input USER_PROD Target] -> #,0.##
- [Input USER_PROD Warn] -> #,0.##
- [Input USER_PROD Crit] -> #,0.##
- [Thr USER_PROD Target] -> #,0.##
- [Thr USER_PROD Warn] -> #,0.##
- [Thr USER_PROD Crit] -> #,0.##
- [Thr Eff Target] -> #,0.##
- [Thr Eff Warn] -> #,0.##
- [Thr Eff Crit] -> #,0.##
