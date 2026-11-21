/* SQL Remediation dialog - one box for: question -> validated SQL, SQL -> validated or converted, several -> batch.
   Mount: SQLRemDialog.mount(element). Backend: kg_api.py (/rp/chat, /rp/config, /rp/templates, /rp/approve) - local
   http://127.0.0.1:8738 by default, a cloud API via window.RP_API_BASE or localStorage "rp_api".
   The model runs in the cloud (GenAI platform, LangGraph Deep Agent); every SQL passes a read-only guard, a dry-run and a
   capped execution on the chosen replica before it is shown. Evidence opens in the Knowledge Graph page. */
(function () {
  var API = window.RP_API_BASE || (window.localStorage && localStorage.getItem("rp_api")) || "http://127.0.0.1:8738";
  var SITES = [["RTCIS_EUS", "RTCIS \u00b7 Euskirchen", "RTCIS", ""], ["RTCIS_LON", "RTCIS \u00b7 London", "RTCIS", ""],
               ["PRIME14_XQ", "PrIME 2014 \u00b7 Xiqing", "PrIME2014", "CN74"],
               ["PRIME22_DE08", "PrIME 2022 \u00b7 Euskirchen DE08", "PrIME2022", "DE08"], ["PRIME22_WMD1", "PrIME 2022 \u00b7 Athens WMD1", "PrIME2022", "WMD1"]];
  var SQL_START = /^\s*(?:(?:--[^\n]*\n)|(?:\/\*[\s\S]*?\*\/))*\s*(select|with)\b/i;
  var BOX = "width:100%;min-height:120px;font-family:Consolas,monospace;font-size:.8rem;padding:.6rem;border:1px solid var(--border,#e3e6ea);border-radius:.6rem";

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function api(path, body) {
    var o = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(API + path, o).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status)); return j; }); });
  }
  function opt(v, t, sel) { return '<option value="' + esc(v) + '"' + (sel ? " selected" : "") + ">" + esc(t) + "</option>"; }
  function siteOpts(def) { return SITES.map(function (s) { return opt(s[0], s[1], s[0] === def); }).join(""); }
  function engineOf(site) { for (var i = 0; i < SITES.length; i++) if (SITES[i][0] === site) return SITES[i][2]; return ""; }
  function whOf(site) { for (var i = 0; i < SITES.length; i++) if (SITES[i][0] === site) return SITES[i][3]; return ""; }
  function chip(status) {
    var cls = /^validated$/.test(status) ? "chip--success" : /validated/.test(status) ? "chip--warning" : /^(ask|convert|validate|batch)/.test(status) ? "chip--neutral" : "chip--danger";
    return '<span class="chip ' + cls + '">' + esc(status) + "</span>";
  }
  function table(cols, rows, empty) {
    if (!cols || !cols.length) return "";
    empty = empty || [];
    var h = cols.map(function (c) { var e = empty.indexOf(c) >= 0; return '<th style="text-align:left;padding:.25rem .4rem;' + (e ? "background:#fee2e2" : "") + '">' + esc(c) + (e ? " \u26a0" : "") + "</th>"; }).join("");
    var b = (rows || []).slice(0, 20).map(function (r) { return "<tr>" + r.map(function (v) { return '<td style="padding:.2rem .4rem;border-top:1px solid #eef1f5">' + esc(v) + "</td>"; }).join("") + "</tr>"; }).join("");
    return '<div style="overflow:auto;max-height:260px;margin-top:.4rem;font-size:.76rem"><table style="border-collapse:collapse;width:100%"><thead><tr>' + h + "</tr></thead><tbody>" + b + "</tbody></table></div>";
  }
  function validationHtml(v) {
    if (!v) return "";
    if (!v.ok) return '<div class="gl-offline" style="margin-top:.4rem;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:.5rem .7rem;border-radius:.5rem">Database said at <b>' + esc(v.stage) + "</b>: " + esc(v.error) + "</div>";
    return '<div class="card__desc" style="margin-top:.4rem">' + esc(v.row_count) + (v.truncated ? "+" : "") + " rows on <b>" + esc(v.site) + "</b> in " + esc(v.seconds) + " s"
      + (v.empty_fields && v.empty_fields.length ? ' &middot; <span style="color:#b91c1c">empty in every row: ' + esc(v.empty_fields.join(", ")) + "</span>" : "") + "</div>"
      + table(v.columns, v.rows, v.empty_fields);
  }
  function evidenceLinks(r) {
    var ids = ((r.evidence && r.evidence.nodes) || []).map(function (n) { return n.id; }).filter(function (i) { return /^Table:/.test(i); }).slice(0, 8);
    if (!ids.length) return "";
    return '<div class="card__desc" style="margin-top:.4rem">Evidence in the graph: ' + ids.map(function (i) {
      var t = i.split(":")[2];
      return '<a class="chip chip--neutral" style="text-decoration:none" target="_blank" href="knowledge-graph.html#rp:versions:' + encodeURIComponent(t) + '">' + esc(i.split(":")[1] + " " + t) + "</a>";
    }).join(" ") + "</div>";
  }
  function resultHtml(r) {
    var h = chip(r.status) + ' <span class="card__desc">' + (r.kind === "validate" ? "" : "SQL runs: " + esc(r.attempts)) + (r.agent_seconds ? " \u00b7 agent " + esc(r.agent_seconds) + " s" : "") + "</span>";
    (r.warnings || []).forEach(function (w) { h += '<div class="card__desc" style="color:#9a3412">\u26a0 ' + esc(w) + "</div>"; });
    if (r.contract) h += '<div class="card__desc">Column contract: ' + (r.contract.identical ? '<b style="color:#15803d">identical</b>' : "missing " + esc((r.contract.missing || []).join(", ")) + " \u00b7 extra " + esc((r.contract.extra || []).join(", "))) + "</div>";
    if (r.source_validation && !r.source_validation.ok) h += '<div class="card__desc" style="color:#9a3412">Source did not run on its engine: ' + esc(r.source_validation.error) + "</div>";
    if (r.sql) h += '<pre style="white-space:pre-wrap;background:#0f172a;color:#e2e8f0;padding:.6rem;border-radius:.5rem;font-size:.76rem;margin-top:.4rem">' + esc(r.sql) + "</pre>";
    var expl = (r.answer || "").replace(/```[\s\S]*?```/g, "").trim();
    if (expl) h += '<div class="card__desc" style="white-space:pre-wrap">' + esc(expl.slice(0, 900)) + "</div>";
    if (r.trace && r.trace.length) h += '<details class="card__desc"><summary>Agent steps (' + r.trace.length + ")</summary>" + r.trace.map(function (t) { return "<div><code>" + esc(t.tool) + "</code> " + esc(t.args) + "</div>"; }).join("") + "</details>";
    h += validationHtml(r.validation) + evidenceLinks(r);
    if (r.status === "validated" && r.kind === "ask") h += '<div style="margin-top:.4rem"><button class="btn" data-ap="1">Approve as example</button></div>';
    return h;
  }

  function mount(root) {
    if (!root) return;
    var turns = [], online = false;
    function $(id) { return root.querySelector("#" + id); }
    function whBox(id, site, hidden) { return '<input id="' + id + '-wh" value="' + esc(whOf(site)) + '" placeholder="wh_id" title="warehouse id (@wh_id)" style="width:78px' + (hidden ? ";display:none" : "") + '"/>'; }
    root.innerHTML =
      '<div class="card" style="margin-bottom:var(--space-5)">'
      + '<div class="flex items-center gap-3" style="justify-content:space-between;flex-wrap:wrap">'
      +   '<div><div class="section__eyebrow">Ask &middot; convert &middot; validate &mdash; run on a real replica</div>'
      +   '<p class="card__desc" style="margin:.3rem 0 0;max-width:86ch"><b>Question</b> &rarr; SQL. <b>SQL</b> &rarr; validated, or converted when <i>Convert to</i> is another database. '
      +   'Several questions or SQL split by <code>---</code> / <code>GO</code> &rarr; batch (max 25). Ctrl+Enter sends.</p></div>'
      +   '<div class="card__desc" id="sr-cfg" style="text-align:right">connecting\u2026</div>'
      + "</div>"
      + '<div id="sr-offline" style="display:none;margin-top:.6rem;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;padding:.6rem .8rem;border-radius:.6rem;font-size:.85rem">'
      +   "<b>Not connected</b> to the SQL Remediation API (<code>" + esc(API) + "</code>). Local: run <code>tools\\kg_api.py</code>; cloud: set <code>localStorage.rp_api</code>.</div>"
      + '<div class="kgf-ctrl" style="margin:.6rem 0 .4rem;display:flex;gap:.5rem;flex-wrap:wrap;align-items:center">Run on <select id="sr-site">' + siteOpts("RTCIS_EUS") + "</select>" + whBox("sr-site", "RTCIS_EUS")
      +   ' &nbsp;Convert to <select id="sr-dst"><option value="">same database (no conversion)</option>' + siteOpts("PRIME22_DE08") + "</select>" + whBox("sr-dst", "PRIME22_DE08")
      +   ' <select id="sr-tpl"><option value="">insert a validated template\u2026</option></select></div>'
      + '<textarea id="sr-text" style="' + BOX + '" placeholder="How many pallets are stored per location area?  |  SELECT ... (paste SQL)  |  several questions, one per line ending with ?">SELECT equip, equip_desc FROM [EUSKIRCHEN_simp].live3.equip</textarea>'
      + '<div style="margin-top:.4rem;display:flex;gap:.5rem;align-items:center"><button class="btn btn--primary" id="sr-go">Send</button><span class="card__desc" id="sr-hint"></span><span style="flex:1"></span>'
      +   '<button class="btn" id="sr-dl" disabled>Download JSON</button><button class="btn" id="sr-csv" disabled>Download CSV</button><button class="btn" id="sr-clear">Clear</button></div>'
      + '<div id="sr-thread" style="margin-top:.6rem"></div></div>';

    function params(id) { var b = $(id + "-wh"); var w = b ? b.value.trim() : ""; return w ? { wh_id: w } : null; }
    function hint() {
      var t = $("sr-text").value.trim(), dst = $("sr-dst").value, site = $("sr-site").value, sql = SQL_START.test(t);
      var many = sql ? /^\s*(?:-{3,}|go)\s*$/im.test(t) : t.split(/\n/).filter(function (x) { return x.trim(); }).length > 1;
      var act = sql ? (dst && dst !== site ? "convert " + engineOf(site) + " \u2192 " + engineOf(dst) : "validate on " + site) : "ask on " + site;
      $("sr-hint").textContent = t ? "\u2192 " + (many ? "batch: " : "") + act : "";
    }
    function send() {
      var text = $("sr-text").value.trim(), site = $("sr-site").value, dst = $("sr-dst").value;
      if (!text) return;
      var box = document.createElement("div");
      box.className = "card sr-turn"; box.style.cssText = "margin-top:.6rem;padding:.8rem;background:#f8fafc";
      box.innerHTML = '<div class="card__desc" style="white-space:pre-wrap;font-family:Consolas,monospace;font-size:.76rem;max-height:120px;overflow:auto">' + esc(text) + '</div><div class="sr-out"></div>';
      $("sr-thread").insertBefore(box, $("sr-thread").firstChild);
      var out = box.querySelector(".sr-out");
      if (!online) { out.innerHTML = '<div class="card__desc" style="color:#9a3412">Needs the API (see the note above).</div>'; return; }
      out.innerHTML = '<div class="card__desc">Working on ' + esc(site) + (dst && dst !== site ? " \u2192 " + esc(dst) : "") + ": knowledge graph \u2192 cloud model \u2192 guard \u2192 dry-run \u2192 execution\u2026</div>";
      var sp = params("sr-site");
      api("/rp/chat", { text: text, site: site, target_site: dst || null, params: sp, target_params: dst ? params("sr-dst") : null }).then(function (r) {
        turns.push(r); $("sr-dl").disabled = $("sr-csv").disabled = false;
        var head = '<div style="margin:.4rem 0">' + chip(r.mode.replace("_", " ")) + " " + Object.keys(r.summary).map(function (k) { return chip(k) + " " + r.summary[k]; }).join(" ") + "</div>";
        out.innerHTML = head + r.results.map(function (it, i) {
          return '<div class="sr-item" data-i="' + i + '" style="border-top:1px solid #e2e8f0;padding-top:.4rem;margin-top:.4rem">'
            + (r.results.length > 1 ? '<div class="card__desc"><b>' + (i + 1) + ".</b> " + esc((it.question || it.source || it.sql || "").slice(0, 120)) + "</div>" : "") + resultHtml(it) + "</div>";
        }).join("");
        out.querySelectorAll(".sr-item").forEach(function (el) {
          var it = r.results[+el.getAttribute("data-i")], ap = el.querySelector("[data-ap]");
          if (ap) ap.onclick = function () {
            api("/rp/approve", { question: it.question, engine: engineOf(site), sql: it.sql, site: site, params: sp })
              .then(function () { ap.textContent = "Approved \u2713 (used as an example)"; ap.disabled = true; }).catch(function (e) { ap.textContent = e.message; });
          };
        });
      }).catch(function (e) { out.innerHTML = '<div class="card__desc" style="color:#b91c1c">' + esc(e.message) + "</div>"; });
    }
    function download(name, text, type) { var a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: type })); a.download = name; a.click(); }

    $("sr-site").addEventListener("change", function () { $("sr-site-wh").value = whOf(this.value); hint(); });
    $("sr-dst").addEventListener("change", function () { var b = $("sr-dst-wh"); b.value = whOf(this.value); b.style.display = this.value ? "" : "none"; hint(); });
    $("sr-text").addEventListener("input", hint);
    $("sr-text").addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); });
    $("sr-go").onclick = send;
    $("sr-clear").onclick = function () { $("sr-thread").innerHTML = ""; turns = []; $("sr-dl").disabled = $("sr-csv").disabled = true; };
    $("sr-dl").onclick = function () { download("sql-remediation-results.json", JSON.stringify(turns, null, 1), "application/json"); };
    $("sr-csv").onclick = function () {
      // a leading = + - @ tab or CR would be run as a formula by Excel / Sheets: prefix with '
      var q = function (s) { var v = String(s == null ? "" : s); if (/^[=+\-@\t\r]/.test(v)) v = "'" + v; return '"' + v.replace(/"/g, '""') + '"'; };
      var lines = [["turn", "mode", "item", "status", "sql_runs", "rows", "error", "empty_fields", "sql"].join(",")];
      turns.forEach(function (t, n) {
        t.results.forEach(function (it) {
          var v = it.validation || {};
          lines.push([n + 1, t.mode, q(it.question || it.source || it.sql), q(it.status), it.attempts || "", v.row_count || "", q(v.error || ""), q((v.empty_fields || []).join(" ")), q(it.sql)].join(","));
        });
      });
      download("sql-remediation-results.csv", lines.join("\n"), "text/csv");
    };
    hint();
    api("/rp/config").then(function (c) {
      online = true;
      $("sr-cfg").innerHTML = "model <b>" + esc(c.model || "?") + "</b> (cloud)<br/>replica: <b>" + esc(c.replica) + "</b>";
      api("/rp/templates").then(function (ts) {
        $("sr-tpl").innerHTML = '<option value="">insert a validated template\u2026</option>' + ts.map(function (t, i) {
          return opt(String(i), t.qid + " \u00b7 " + (t.engine === "RTCIS" ? "RTCIS" : "PrIME 2022") + " \u00b7 " + (t.title || "").slice(0, 38)); }).join("");
        $("sr-tpl").onchange = function () {
          var t = ts[+this.value]; if (!t) return;
          $("sr-text").value = t.sql; $("sr-site").value = t.engine === "RTCIS" ? "RTCIS_EUS" : "PRIME22_DE08";
          $("sr-site-wh").value = whOf($("sr-site").value); this.value = ""; hint();
        };
      });
    }).catch(function () { $("sr-cfg").textContent = "offline"; $("sr-offline").style.display = ""; });
  }

  window.SQLRemDialog = { mount: mount };
})();
