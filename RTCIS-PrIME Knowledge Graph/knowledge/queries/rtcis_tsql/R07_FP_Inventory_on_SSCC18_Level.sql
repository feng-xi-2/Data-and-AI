-- R07 FP Inventory on SSCC18 level (RTCIS, already T-SQL; schema-qualified). SSRS multi-value params tested single-valued.
-- Params: @subsit, @itmcod (LIKE), @grpdsc, @ulid (LIKE), @locatn (LIKE)
select su.sitnam "Subsit", iv.blding Building, iv.locatn Location, iv.ulid20 "Pallet Number", iv.ulpall "Pallet Type",
       iv.itmcod "Item Code", it.itmdsc "Item Description", ig.grpdsc "Item Group Description", iv.ctlgrp "Control Group",
       it.itmnum "Categorie", cg.vndlot "Vendor Lot", cg.qastat "QA Status", iv.casqty "Quantity", uo.uom "WHSE Unit",
       cg.FIFODT "First Receipt Date",
       getDate() AT TIME ZONE 'UTC' AT TIME ZONE 'Central Europe Standard Time' as sysdate
from EUSKIRCHEN.LIVE3.AGV_INVENTORY_VIEW iv
inner join EUSKIRCHEN.live3.ctlgrp cg on iv.itmcod = cg.itmcod and iv.itmcls = cg.itmcls and iv.ctlgrp = cg.ctlgrp
inner join EUSKIRCHEN.live3.ITMMST it on cg.itmcls = it.itmcls and cg.itmcod = it.itmcod
inner join EUSKIRCHEN.live3.itmgrp ig on it.itmcls = ig.itmcls and it.itmgrp = ig.itmgrp
inner join EUSKIRCHEN.live3.subsit su on iv.subsit = su.subsit
inner join EUSKIRCHEN.live3.item_uom uo on it.itmcls = uo.itmcls and it.itmcod = uo.itmcod and uo.whsflg = 'Y'
where iv.itmcls = 'F'
  and su.subsit in (@subsit)
  and iv.itmcod like @itmcod
  and ig.grpdsc in (@grpdsc)
  and iv.ulid20 like @ulid
  and iv.locatn like @locatn;
