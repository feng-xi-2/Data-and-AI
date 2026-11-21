-- R16 RPM inventory on SSCC18 level (RTCIS, already T-SQL; schema-qualified). Params: @subsit, @itmcod, @grpdsc, @ulid
select su.sitnam "Subsit", iv.blding Building, iv.locatn Location, iv.ulid20 "Pallet Number", iv.ulpall "Pallet Type",
       iv.itmcod "Item Code", it.itmdsc "Item Description",
       Case When ig.itmgrp = 'WIR007' and substring(iv.locatn, 1, 3) = 'HOF' then 'BW-SUBSTRATE-EX' else ig.grpdsc End "Item Group Description",
       iv.ctlgrp "Control Group", cg.VNDCOD "Vendor Cod", cg.vndlot "Vendor Lot", cg.qastat "QA Status", iv.casqty "Quantity",
       cg.FIFODT "First Receipt Date", cg.PONUMB "PO Number", iv.ctrl_date,
       getDate() AT TIME ZONE 'UTC' AT TIME ZONE 'Central Europe Standard Time' as sysdate
from EUSKIRCHEN.LIVE3.AGV_INVENTORY_VIEW iv
inner join EUSKIRCHEN.live3.ctlgrp cg on iv.itmcod = cg.itmcod and iv.itmcls = cg.itmcls and iv.ctlgrp = cg.ctlgrp
inner join EUSKIRCHEN.live3.ITMMST it on cg.itmcls = it.itmcls and cg.itmcod = it.itmcod
inner join EUSKIRCHEN.live3.itmgrp ig on it.itmcls = ig.itmcls and it.itmgrp = ig.itmgrp
inner join EUSKIRCHEN.live3.subsit su on iv.subsit = su.subsit
where iv.itmcls = 'P' and su.subsit in (@subsit) and iv.itmcod like @itmcod and ig.grpdsc in (@grpdsc) and iv.ulid20 like @ulid;
