/* RTCIS <-> PrIME 2014 <-> PrIME 2022 tab of knowledge-graph.html.
   Same force-directed visual as the other tabs (window.__KG.makeGraph). Data: kg_api.py on 127.0.0.1:8738, which reads
   Cosmos DB (Gremlin graph whs_kg/rtcis_prime), asks the GenAI model and validates every SQL on the replica databases.
   Offline: window.RP_VIEWS (assets/rtcis-prime-views.js) holds real views exported from Cosmos; ask/convert need the API. */
(function () {
  var API = "http://127.0.0.1:8738";
  var pane = document.getElementById("kgtab-rp");
  var K = window.__KG;
  if (!pane || !K) return;
  var esc = function (s) { return K.esc(s).replace(/"/g, "&quot;").replace(/'/g, "&#39;"); }, kpi = K.kpi, num = K.num;
  var VIEWS = window.RP_VIEWS || { views: {} };
  var COL = {
    "RTCIS table": "#b4690e", "RTCIS column": "#f2b766", "PrIME 2014 table": "#7c3aed", "PrIME 2014 column": "#c4b5fd",
    "PrIME 2022 table": "#2563eb", "PrIME 2022 column": "#93c5fd", "Platform": "#475569", "Query": "#0f766e",
    "OutputField": "#14b8a6", "ExpertRule": "#c4314b", "Finding": "#db2777", "SDCModule": "#16a34a", "PMCProcess": "#65a30d",
    "Domain": "#0891b2", "Learning": "#9333ea", "DataFact": "#d97706", "Concept": "#64748b"
  };
  Object.keys(COL).forEach(function (k) { K.labelColor[k] = COL[k]; });
  var SITES = [["PRIME22_DE08", "PrIME 2022 \u00b7 Euskirchen DE08", "PrIME2022", "DE08"], ["PRIME22_WMD1", "PrIME 2022 \u00b7 Athens WMD1", "PrIME2022", "WMD1"],
               ["PRIME14_XQ", "PrIME 2014 \u00b7 Xiqing", "PrIME2014", "CN74"], ["RTCIS_EUS", "RTCIS \u00b7 Euskirchen", "RTCIS", ""], ["RTCIS_LON", "RTCIS \u00b7 London", "RTCIS", ""]];
  var TEMPLATES = [
    ["versions", "One table across RTCIS \u2192 PrIME 2014 \u2192 PrIME 2022", ["invlod", "locmst", "prtmst", "pckwrk_dtl", "shipment", "rcvlin", "unitld", "itmmst"]],
    ["query", "Query conversion lineage (RTCIS \u2192 PrIME, fields, rules, findings)", ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R13", "R14", "R15", "R16", "R17"]],
    ["sdc", "SDC module / PMC process \u2192 tables in both engines", ["01", "02", "03", "04", "05", "07", "08", "10", "PMC-03.02.01", "PMC-05.02.01", "PMC-02.01.01"]],
    ["domain", "Business domain \u2192 tables in the three engines", ["inventory", "receiving", "picking", "shipment", "location", "counting", "work", "trailer"]],
    ["issues", "Open issues: mapping conflicts & code sets that differ", [""]],
    ["rules", "Expert rules (Gino OBS1-8) \u2192 queries that pass them", [""]]
  ];
  var ONLINE = false, G = null, built = false, last = {};

  function api(path, body) {
    var o = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(API + path, o).then(function (r) {
      return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; });
    });
  }
  function opt(v, t, sel) { return '<option value="' + esc(v) + '"' + (sel ? " selected" : "") + ">" + esc(t) + "</option>"; }
  function siteOpts(def, engine) {
    return SITES.filter(function (s) { return !engine || s[2] === engine; }).map(function (s) { return opt(s[0], s[1], s[0] === def); }).join("");
  }
  function engineOf(site) { for (var i = 0; i < SITES.length; i++) if (SITES[i][0] === site) return SITES[i][2]; return "PrIME2022"; }
  function whOf(site) { for (var i = 0; i < SITES.length; i++) if (SITES[i][0] === site) return SITES[i][3]; return ""; }
  function params(selId) { var b = $(selId + "-wh"), w = b ? b.value.trim() : whOf($(selId).value); return w ? { wh_id: w } : null; }
  function wh(selId, site) { return '<input id="' + selId + '-wh" value="' + esc(whOf(site)) + '" placeholder="wh_id" title="warehouse id (@wh_id)" style="width:78px"/>'; }
  function chip(status) {
    var cls = /^validated$/.test(status) ? "chip--success" : /validated/.test(status) ? "chip--warning" : "chip--danger";
    return '<span class="chip ' + cls + '">' + esc(status) + "</span>";
  }
  var BOX = 'style="width:100%;min-height:92px;font-family:Consolas,monospace;font-size:.8rem;padding:.5rem;border:1px solid var(--border,#e3e6ea);border-radius:.5rem"';

  pane.innerHTML =
    '<div id="rp-offline" class="gl-offline" style="display:none;margin-bottom:var(--space-5)"><b>RTCIS \u2194 PrIME API not reachable.</b> Showing graph views exported from Cosmos DB. '
    + 'Ask / convert / batch / validate need the API (it calls the GenAI model and the replica databases):<br/><br/>'
    + "<code>cd _kg_cosmos</code><br/><code>. .\\env.local.ps1</code><br/><code>& $py tools\\kg_api.py</code><br/><br/>Then reload. (API: <code>" + API + "</code>)</div>"
    + '<div class="kpi-row" id="rp-kpis" style="margin-bottom:var(--space-5)"></div>'
    /* graph templates */
    + '<div class="card" style="margin-bottom:var(--space-5)">'
    +   '<div class="flex items-center gap-3" style="justify-content:space-between;flex-wrap:wrap">'
    +     '<div><div class="section__eyebrow">Cosmos DB graph &middot; validated against the replica databases</div>'
    +     '<p class="card__desc" style="margin:.3rem 0 0;max-width:72ch">Pick a graph template. Colours = engine: <b style="color:#b4690e">RTCIS</b>, <b style="color:#7c3aed">PrIME 2014</b>, <b style="color:#2563eb">PrIME 2022</b>; darker = table, lighter = column. Every table/column exists in a live catalog; MAPS_TO edges carry their value check. Drag nodes; click to inspect.</p></div>'
    +     '<div class="kgf-ctrl"><select id="rp-tmpl">' + TEMPLATES.map(function (t) { return opt(t[0], t[1]); }).join("") + '</select>'
    +       '<select id="rp-key"></select><input id="rp-free" placeholder="or type a table / R16 / PMC" style="width:190px"/><button class="btn" id="rp-load">Show</button></div>'
    +   "</div>"
    +   '<div id="rp-meta" class="card__desc" style="margin:.4rem 0"></div>'
    +   '<div class="kgf-wrap"><svg id="rp-svg" class="kgf-svg"></svg><div id="rp-legend" class="kgf-legend"></div><div id="rp-panel" class="kgf-panel"></div></div>'
    + "</div>"
    /* ask + convert */
    + '<div class="grid grid--2" style="margin-bottom:var(--space-5)">'
    +   '<div class="card"><div class="section__eyebrow">Ask in natural language &rarr; validated SQL</div>'
    +     '<p class="card__desc" style="margin:.3rem 0 .5rem">The graph links your words to real tables, columns, validated example queries and expert learnings; the model writes one read-only SELECT; it is dry-run and executed (max 50 rows) on the chosen database, with one automatic repair round.</p>'
    +     '<div class="kgf-ctrl" style="margin-bottom:.4rem"><select id="rp-ask-site">' + siteOpts("PRIME22_DE08") + "</select>" + wh("rp-ask-site", "PRIME22_DE08") + "</div>"
    +     '<textarea id="rp-ask-q" ' + BOX + '>How many pallets (loads) are stored per location area?</textarea>'
    +     '<div class="kgf-ctrl" style="margin-top:.4rem"><button class="btn" id="rp-ask-go">Ask &amp; validate</button></div><div id="rp-ask-out"></div></div>'
    +   '<div class="card"><div class="section__eyebrow">Convert a query between engines</div>'
    +     '<p class="card__desc" style="margin:.3rem 0 .5rem">The source runs on its own engine first (output columns = the contract). The graph supplies value-validated column mappings and rules; the result is validated on the target and the column contract compared.</p>'
    +     '<div class="kgf-ctrl" style="margin-bottom:.4rem"><select id="rp-cv-tpl"><option value="">template: none</option></select></div>'
    +     '<div class="kgf-ctrl" style="margin-bottom:.4rem">from <select id="rp-cv-src">' + siteOpts("RTCIS_EUS") + "</select>" + wh("rp-cv-src", "RTCIS_EUS") + ' to <select id="rp-cv-dst">' + siteOpts("PRIME22_DE08") + "</select>" + wh("rp-cv-dst", "PRIME22_DE08") + "</div>"
    +     '<textarea id="rp-cv-sql" ' + BOX + '>SELECT equip, equip_desc FROM [EUSKIRCHEN_simp].live3.equip</textarea>'
    +     '<div class="kgf-ctrl" style="margin-top:.4rem"><button class="btn" id="rp-cv-go">Convert &amp; validate</button></div><div id="rp-cv-out"></div></div>'
    + "</div>"
    /* batch + validate */
    + '<div class="grid grid--2">'
    +   '<div class="card"><div class="section__eyebrow">Batch (max 25)</div>'
    +     '<p class="card__desc" style="margin:.3rem 0 .5rem">Questions: one per line. SQL to convert: separate queries with a line <code>---</code> or <code>GO</code>. Every item is validated on the database; download the results.</p>'
    +     '<div class="kgf-ctrl" style="margin-bottom:.4rem"><select id="rp-b-kind">' + opt("ask", "questions \u2192 SQL") + opt("convert", "convert SQL") + '</select>'
    +       '<select id="rp-b-site">' + siteOpts("PRIME22_DE08") + "</select>" + wh("rp-b-site", "PRIME22_DE08") + '<span id="rp-b-to" style="display:none">to <select id="rp-b-dst">' + siteOpts("PRIME22_DE08") + "</select>" + wh("rp-b-dst", "PRIME22_DE08") + "</span></div>"
    +     '<textarea id="rp-b-text" ' + BOX + '>How many loads are in each location area?\nWhich parts have no footprint detail?\nOpen pick work per wave</textarea>'
    +     '<div class="kgf-ctrl" style="margin-top:.4rem"><button class="btn" id="rp-b-go">Run batch</button><button class="btn" id="rp-b-dl" disabled>Download JSON</button><button class="btn" id="rp-b-csv" disabled>Download CSV</button></div><div id="rp-b-out"></div></div>'
    +   '<div class="card"><div class="section__eyebrow">Validate SQL on a real database</div>'
    +     '<p class="card__desc" style="margin:.3rem 0 .5rem">Read-only guard (sqlglot) &rarr; dry-run (describe_first_result_set) &rarr; capped execution. Columns empty in every row are flagged (rule E1).</p>'
    +     '<div class="kgf-ctrl" style="margin-bottom:.4rem"><select id="rp-v-site">' + siteOpts("PRIME22_DE08") + "</select>" + wh("rp-v-site", "PRIME22_DE08") + "</div>"
    +     '<textarea id="rp-v-sql" ' + BOX + ">SELECT TOP 20 LODNUM, STOLOC, WH_ID FROM dbo.invlod WHERE WH_ID = @wh_id</textarea>"
    +     '<div class="kgf-ctrl" style="margin-top:.4rem"><button class="btn" id="rp-v-go">Validate</button></div><div id="rp-v-out"></div></div>'
    + "</div>";

  function $(id) { return document.getElementById(id); }
  function setKeys() {
    var t = $("rp-tmpl").value, keys = [];
    TEMPLATES.forEach(function (x) { if (x[0] === t) keys = x[2]; });
    $("rp-key").innerHTML = keys.map(function (k) { return opt(k, k || "(all)"); }).join("");
    $("rp-key").style.display = keys.length > 1 ? "" : "none";
  }
  function showGraph(g, note) {
    if (!G) G = K.makeGraph($("rp-svg"), $("rp-legend"), $("rp-panel"));
    if (!g || !g.nodes || !g.nodes.length) { $("rp-panel").innerHTML = '<div class="card__desc">No nodes for this template / key.</div>'; return; }
    G.build(g);
    $("rp-meta").innerHTML = (note || "") + " " + g.nodes.length + " nodes &middot; " + (g.edges || []).length + " edges.";
    $("rp-panel").innerHTML = '<div class="card__desc">Click a node to inspect its properties (validation evidence included).</div>';
  }
  function load() {
    var view = $("rp-tmpl").value, key = ($("rp-free").value || "").trim() || $("rp-key").value || "";
    if (/^R\d\d$/i.test(key)) view = "query";
    else if (/^PMC/i.test(key) || /^\d\d$/.test(key)) view = "sdc";
    var id = view + ":" + key;
    if (!ONLINE) {
      var g = VIEWS.views[id];
      showGraph(g, g ? "Snapshot from Cosmos (" + esc(VIEWS.generatedAt || "") + ")." : "");
      if (!g) $("rp-meta").innerHTML = "Not in the offline snapshot - start the API for any table / query / PMC. Snapshot has: " + esc(Object.keys(VIEWS.views).join(", "));
      return;
    }
    $("rp-meta").innerHTML = "Loading from Cosmos DB\u2026";
    api("/rp/graph?view=" + encodeURIComponent(view) + "&key=" + encodeURIComponent(key)).then(function (g) { showGraph(g, "Live from Cosmos DB."); })
      .catch(function (e) { $("rp-meta").innerHTML = '<span class="gl-offline">' + esc(e.message) + "</span>"; });
  }

  function table(cols, rows, empty) {
    if (!cols || !cols.length) return "";
    empty = empty || [];
    var h = cols.map(function (c) { return '<th style="text-align:left;padding:.25rem .4rem;' + (empty.indexOf(c) >= 0 ? "background:#fee2e2" : "") + '">' + esc(c) + (empty.indexOf(c) >= 0 ? " \u26a0" : "") + "</th>"; }).join("");
    var b = (rows || []).slice(0, 20).map(function (r) { return "<tr>" + r.map(function (v) { return '<td style="padding:.2rem .4rem;border-top:1px solid #eef1f5">' + esc(v) + "</td>"; }).join("") + "</tr>"; }).join("");
    return '<div style="overflow:auto;max-height:260px;margin-top:.4rem;font-size:.76rem"><table style="border-collapse:collapse;width:100%"><thead><tr>' + h + "</tr></thead><tbody>" + b + "</tbody></table></div>";
  }
  function validationHtml(v) {
    if (!v) return "";
    if (!v.ok) return '<div class="gl-offline" style="margin-top:.4rem">Database said at <b>' + esc(v.stage) + "</b>: " + esc(v.error) + "</div>";
    return '<div class="card__desc" style="margin-top:.4rem">' + num(v.row_count) + (v.truncated ? "+" : "") + " rows on <b>" + esc(v.site) + "</b> in " + esc(v.seconds) + " s"
      + (v.empty_fields && v.empty_fields.length ? ' &middot; <span style="color:#b91c1c">empty in every row: ' + esc(v.empty_fields.join(", ")) + "</span>" : "") + "</div>"
      + table(v.columns, v.rows, v.empty_fields);
  }
  function resultHtml(r, kind) {
    var h = chip(r.status) + ' <span class="card__desc">attempts: ' + esc(r.attempts) + "</span>";
    (r.warnings || []).forEach(function (w) { h += '<div class="card__desc" style="color:#9a3412">\u26a0 ' + esc(w) + "</div>"; });
    if (r.contract) h += '<div class="card__desc">Column contract: ' + (r.contract.identical ? "<b style=\"color:#15803d\">identical</b>" : "missing " + esc((r.contract.missing || []).join(", ")) + " \u00b7 extra " + esc((r.contract.extra || []).join(", "))) + "</div>";
    if (r.source_validation && !r.source_validation.ok) h += '<div class="gl-offline">Source did not run on its engine: ' + esc(r.source_validation.error) + "</div>";
    h += '<pre style="white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:.6rem;border-radius:.5rem;font-size:.76rem;margin-top:.4rem">' + esc(r.sql) + "</pre>";
    h += validationHtml(r.validation);
    h += '<div class="kgf-ctrl" style="margin-top:.4rem"><button class="btn" data-ev="1">Show evidence in graph</button>' + (r.status === "validated" && kind === "ask" ? '<button class="btn" data-ap="1">Approve as example</button>' : "") + "</div>";
    return h;
  }
  function wire(out, r, kind, question, site) {
    var ev = out.querySelector("[data-ev]"), ap = out.querySelector("[data-ap]");
    if (ev) ev.onclick = function () { showGraph(r.evidence, "Evidence used for this answer."); $("rp-svg").scrollIntoView({ behavior: "smooth", block: "center" }); };
    if (ap) ap.onclick = function () {
      api("/rp/approve", { question: question, engine: engineOf(site), sql: r.sql, site: site }).then(function () { ap.textContent = "Approved \u2713 (used as few-shot)"; ap.disabled = true; })
        .catch(function (e) { ap.textContent = e.message; });
    };
  }
  function busy(el, txt) { el.innerHTML = '<div class="card__desc">' + txt + "</div>"; }
  function need(el) { if (ONLINE) return true; el.innerHTML = '<div class="gl-offline">Needs the API (see the note at the top of this tab).</div>'; return false; }

  function bind() {
    ["rp-ask-site", "rp-cv-src", "rp-cv-dst", "rp-b-site", "rp-b-dst", "rp-v-site"].forEach(function (id) {
      $(id).addEventListener("change", function () { var b = $(id + "-wh"); if (b) b.value = whOf(this.value); });
    });
    $("rp-tmpl").onchange = function () { $("rp-free").value = ""; setKeys(); load(); };
    $("rp-key").onchange = function () { $("rp-free").value = ""; load(); };
    $("rp-load").onclick = load;
    $("rp-ask-go").onclick = function () {
      var out = $("rp-ask-out"), site = $("rp-ask-site").value, q = $("rp-ask-q").value.trim();
      if (!need(out) || !q) return;
      busy(out, "Linking the question to the graph, asking the model, validating on " + esc(site) + "\u2026");
      api("/rp/ask", { question: q, engine: engineOf(site), site: site, params: params("rp-ask-site") }).then(function (r) { last.ask = r; out.innerHTML = resultHtml(r, "ask"); wire(out, r, "ask", q, site); })
        .catch(function (e) { out.innerHTML = '<div class="gl-offline">' + esc(e.message) + "</div>"; });
    };
    $("rp-cv-go").onclick = function () {
      var out = $("rp-cv-out"), s = $("rp-cv-src").value, d = $("rp-cv-dst").value;
      if (!need(out)) return;
      busy(out, "Running the source on " + esc(s) + ", converting with graph mappings, validating on " + esc(d) + "\u2026");
      api("/rp/convert", { sql: $("rp-cv-sql").value, source_engine: engineOf(s), target_engine: engineOf(d), source_site: s, target_site: d, params: params("rp-cv-dst"), source_params: params("rp-cv-src") })
        .then(function (r) { out.innerHTML = resultHtml(r, "convert"); wire(out, r, "convert"); })
        .catch(function (e) { out.innerHTML = '<div class="gl-offline">' + esc(e.message) + "</div>"; });
    };
    $("rp-b-kind").onchange = function () { $("rp-b-to").style.display = this.value === "convert" ? "" : "none"; };
    $("rp-b-go").onclick = function () {
      var out = $("rp-b-out"), kind = $("rp-b-kind").value, s = $("rp-b-site").value, d = $("rp-b-dst").value;
      if (!need(out)) return;
      busy(out, "Running the batch item by item (each one validated on the database)\u2026");
      var body = { kind: kind, text: $("rp-b-text").value, engine: engineOf(s), site: s, params: params(kind === "convert" ? "rp-b-dst" : "rp-b-site") };
      if (kind === "convert") { body.target_engine = engineOf(d); body.target_site = d; }
      api("/rp/batch", body).then(function (r) {
        last.batch = r;
        var sm = Object.keys(r.summary).map(function (k) { return chip(k) + " " + r.summary[k]; }).join(" &nbsp; ");
        var rows = r.items.map(function (it, i) {
          var v = it.validation || {};
          return "<tr><td>" + (i + 1) + "</td><td>" + chip(it.status) + "</td><td>" + esc((it.question || it.source || "").slice(0, 70)) + "</td><td>" + esc(v.ok ? v.row_count : v.error || "") + "</td><td>" + esc((v.empty_fields || []).join(", ")) + "</td></tr>";
        }).join("");
        out.innerHTML = '<div style="margin:.4rem 0">' + sm + '</div><div style="overflow:auto;max-height:300px;font-size:.76rem"><table style="width:100%;border-collapse:collapse"><thead><tr><th>#</th><th>status</th><th>item</th><th>rows / error</th><th>empty fields</th></tr></thead><tbody>' + rows + "</tbody></table></div>";
        $("rp-b-dl").disabled = false; $("rp-b-csv").disabled = false;
      }).catch(function (e) { out.innerHTML = '<div class="gl-offline">' + esc(e.message) + "</div>"; });
    };
    function download(name, text, type) { var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: type })); a.download = name; a.click(); }
    $("rp-b-dl").onclick = function () { download("rtcis-prime-batch.json", JSON.stringify(last.batch, null, 1), "application/json"); };
    $("rp-b-csv").onclick = function () {
      var q = function (s) { return '"' + String(s == null ? "" : s).replace(/"/g, '""') + '"'; };
      var lines = [["item", "status", "attempts", "rows", "error", "empty_fields", "sql"].join(",")].concat(last.batch.items.map(function (it) {
        var v = it.validation || {};
        return [q(it.question || it.source), q(it.status), it.attempts, v.row_count || "", q(v.error || ""), q((v.empty_fields || []).join(" ")), q(it.sql)].join(",");
      }));
      download("rtcis-prime-batch.csv", lines.join("\n"), "text/csv");
    };
    $("rp-v-go").onclick = function () {
      var out = $("rp-v-out"), site = $("rp-v-site").value;
      if (!need(out)) return;
      busy(out, "Validating on " + esc(site) + "\u2026");
      api("/rp/validate", { sql: $("rp-v-sql").value, site: site, params: params("rp-v-site") }).then(function (v) { out.innerHTML = validationHtml(v); })
        .catch(function (e) { out.innerHTML = '<div class="gl-offline">' + esc(e.message) + "</div>"; });
    };
  }

  function kpis(c) {
    var n = (c && c.nodes) || {}, e = (c && c.edges) || {};
    var tot = function (o) { return Object.keys(o).reduce(function (a, k) { return a + o[k]; }, 0); };
    $("rp-kpis").innerHTML = kpi(num(tot(n)), "Vertices") + kpi(num(tot(e)), "Edges") + kpi(num(n.Table || 0), "Tables (3 engines)")
      + kpi(num(e.MAPS_TO || 0), "Validated mappings") + kpi(num((n.Query || 0) / 2), "Converted queries") + kpi(num(n.PMCProcess || 0), "PMC processes");
  }

  function start() {
    bind(); setKeys(); kpis(VIEWS.counts);
    api("/rp/health").then(function (h) {
      ONLINE = true;
      api("/rp/templates").then(function (ts) {
        $("rp-cv-tpl").innerHTML = '<option value="">template: none</option>' + ts.filter(function (t) { return t.engine === "RTCIS"; })
          .map(function (t, i) { return opt(t.qid, t.qid + " \u00b7 " + (t.title || "").slice(0, 40)); }).join("");
        $("rp-cv-tpl").onchange = function () {
          var q = this.value; ts.forEach(function (t) { if (t.qid === q && t.engine === "RTCIS") $("rp-cv-sql").value = t.sql; });
        };
      });
      load();
    }).catch(function () { ONLINE = false; $("rp-offline").style.display = ""; load(); });
  }

  window.RP_TAB = { activate: function (tab) { if (tab === "rp" && !built) { built = true; start(); } } };
  function openFromHash() {
    if (location.hash !== "#rp") return;
    var b = document.querySelector('.kg-tab[data-tab="rp"]');
    if (b) b.click();
  }
  window.addEventListener("hashchange", openFromHash);
  openFromHash();
})();
