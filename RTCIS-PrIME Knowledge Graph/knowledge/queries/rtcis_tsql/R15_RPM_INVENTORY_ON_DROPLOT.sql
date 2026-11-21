-- R15 RPM inventory on drop lot (RTCIS, already T-SQL; schema-qualified). Params: @itmcod (LIKE), @grpdsc
select su.sitnam "Subsit", iv.locatn Location, count(iv.ulid20) "Count_Pallets", iv.itmcod "Item Code", it.itmdsc "Item Description",
       ig.grpdsc "Item Group Description", iv.ctlgrp "Control Group", cg.VNDCOD "Vendor Cod", cg.vndlot "Vendor Lot",
       cg.qastat "QA Status", sum(iv.casqty) "Sum_Quantity", cg.FIFODT "First Receipt Date", cg.PONUMB "PO Number",
       getDate() AT TIME ZONE 'UTC' AT TIME ZONE 'Central Europe Standard Time' as sysdate
from EUSKIRCHEN.LIVE3.AGV_INVENTORY_VIEW iv
inner join EUSKIRCHEN.live3.ctlgrp cg on iv.itmcod = cg.itmcod and iv.itmcls = cg.itmcls and iv.ctlgrp = cg.ctlgrp
inner join EUSKIRCHEN.live3.ITMMST it on cg.itmcls = it.itmcls and cg.itmcod = it.itmcod
inner join EUSKIRCHEN.live3.itmgrp ig on it.itmcls = ig.itmcls and it.itmgrp = ig.itmgrp
inner join EUSKIRCHEN.live3.subsit su on iv.subsit = su.subsit
where iv.itmcls = 'P' and substring(iv.locatn, 1, 3) = 'HOF' and su.subsit = '0'
  and iv.itmcod like @itmcod and ig.grpdsc in (@grpdsc)
group by su.sitnam, iv.locatn, iv.itmcod, it.itmdsc, ig.grpdsc, iv.ctlgrp, cg.VNDCOD, cg.vndlot, cg.qastat, cg.FIFODT, cg.PONUMB;
