# Gremlin traversals for conversion and query writing (Cosmos DB for Apache Gremlin)

Vertex ids: `Table:<side>:<table>`, `Column:<side>:<table>.<column>` with side `rtcis` | `prime14` | `prime` (2022).
Partition key `pk`: `Table:RTCIS`, `Column:PrIME2022` … for the schema, the label for everything else. **Always pass `pk`
on point reads** (`g.V(id).has('pk', …)`) — it avoids a cross-partition fan-out. Bind values as parameters, never concatenate.

## Convert a column
```groovy
// RTCIS column -> PrIME 2022 counterparts, with the evidence on the edge
g.V('Column:rtcis:untdtl.casqty').has('pk','Column:RTCIS')
 .outE('MAPS_TO').as('m').inV().has('platform','PrIME2022')
 .project('to','verdict','sources','type','conflict').by(id).by(select('m').coalesce(values('value_verdict'), values('tag'), constant('')))
 .by(select('m').coalesce(values('sources'), values('agreement'), constant(''))).by(select('m').coalesce(values('type_check'), constant('')))
 .by(select('m').coalesce(values('conflict'), constant('')))

// no direct mapping? 2-hop inference: mapped table, same-named column
g.V('Table:rtcis:locatn').has('pk','Table:RTCIS').out('MAPS_TO').has('platform','PrIME2022')
 .out('HAS_COLUMN').has('name','arecod').values('id')
```

## Convert a query (plan)
```groovy
// tables the RTCIS query reads -> PrIME 2022 tables
g.V('Query:R16:rtcis').has('pk','Query').out('READS').out('MAPS_TO').has('platform','PrIME2022').dedup().values('name')
// learnings / data facts about those tables (inject into the prompt)
g.V('Query:R16:rtcis').has('pk','Query').out('READS').in('MENTIONS').hasLabel('Learning','DataFact').dedup().values('text')
// expert rules the delivered conversion passed, and why fields are empty
g.V('Query:R16:prime').has('pk','Query').outE('APPLIES_RULE').has('result','PASS').inV().values('code')
g.V('Query:R16:prime').has('pk','Query').out('HAS_FIELD').out('EXPLAINED_BY').valueMap('category','text')
```

## Write a new query (schema linking)
```groovy
// replicated PrIME 2022 tables of a domain, with descriptions
g.V('Domain:inventory').has('pk','Domain').in('IN_DOMAIN').has('platform','PrIME2022')
 .where(out('EXISTS_AT').has('id','Site:PRIME22_DE08')).valueMap('name','description','theme')
// columns of a table with descriptions and keys
g.V('Table:prime:invlod').has('pk','Table:PrIME2022').out('HAS_COLUMN').valueMap('name','data_type','description','primary_key')
// a validated template for the intent (then adapt its parameters)
g.V().has('pk','Query').has('side','PrIME2022').has('intent', TextP.containing('nventory')).valueMap('qid','intent','params','grade','file')
```

## PrIME 2014 -> 2022
```groovy
g.V('Column:prime14:prtftp_view.untinp').has('pk','Column:PrIME2014').out('MAPS_TO').values('id')   // renamed columns
g.V().has('pk','Table:PrIME2014').not(outE('MAPS_TO')).values('name')                             // no 2022 counterpart
```

## Governance
```groovy
g.V().has('pk','Column:RTCIS').outE('MAPS_TO').has('conflict').project('from','to','alt').by(outV().id()).by(inV().id()).by('conflict')
g.V().has('pk','Column:RTCIS').outE('MAPS_TO').has('value_verdict', TextP.containing('CODE SET')).project('from','to').by(outV().id()).by(inV().id())
```
Cosmos Gremlin notes: start traversals from a partition (g.V().has('pk', …)), never g.E() / g.V() over the whole graph — at 1,000 RU/s a full scan is throttled; `TextP.containing` is case-sensitive; `id` is a property (use `.id()` or `values('id')`); keep traversals bounded (`limit`) — RU cost grows with every vertex touched.
