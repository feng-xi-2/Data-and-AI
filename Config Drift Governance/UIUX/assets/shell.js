/* =====================================================================
   WHS GenAI — App shell injector
   Renders the Perplexity-style left sidebar (with nested, clickable
   lists of Agents and Workflows/Assistants) into #app-sidebar.
   Active item read from <body data-active="..."> and optional
   <body data-active-id="...">.  Requires data.js loaded first.
   ===================================================================== */
(function () {
  var W = window.WHS || { agents: [], assistants: [] };

  var ICONS = {
    home:  '<path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/>',
    agent: '<rect x="4" y="8" width="16" height="12" rx="2"/><path d="M12 8V4M9 4h6M9 13h.01M15 13h.01M9 17h6"/>',
    puzzle:'<path d="M10 4h4a1 1 0 0 1 1 1v2a2 2 0 1 0 4 0V5"/><path d="M20 9v6a1 1 0 0 1-1 1h-2a2 2 0 1 0 0 4h2"/><path d="M4 15V9a1 1 0 0 1 1-1h2a2 2 0 1 0 0-4H5"/>',
    data:  '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/><path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"/>',
    graph: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="7" r="2.5"/><circle cx="12" cy="17" r="2.5"/><path d="M8 7.5 10.5 15M16 9 13.5 15M8 6.5 16 7"/>',
    layers:'<path d="M12 3 3 8l9 5 9-5z"/><path d="m3 13 9 5 9-5M3 18l9 5 9-5"/>',
    chev:  '<polyline points="9 6 15 12 9 18"/>'
  };

  var AVATAR = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">'
    + '<path d="M7.99963 2.95166C6.46094 2.95166 5.20898 4.20349 5.20898 5.74231C5.20898 7.28101 6.46094 8.53284 7.99963 8.53284C9.53833 8.53284 10.7903 7.28101 10.7903 5.74231C10.7903 4.20349 9.53833 2.95166 7.99963 2.95166Z" fill="#003899"/>'
    + '<path d="M8 0C3.58875 0 0 3.58875 0 8C0 10.041 0.768677 11.9055 2.03113 13.3204C2.30151 12.1332 2.922 11.0499 3.828 10.2061C4.46387 9.61377 5.20789 9.17053 6.01208 8.8949C4.96716 8.23364 4.27185 7.06775 4.27185 5.74243C4.27185 3.68665 5.94434 2.01428 8 2.01428C10.0557 2.01428 11.728 3.68665 11.728 5.74243C11.728 7.06714 11.0333 8.23267 9.98914 8.89404C10.8602 9.19238 11.6587 9.68774 12.329 10.358C13.1479 11.177 13.7134 12.2064 13.9683 13.3209C15.2312 11.906 16 10.0413 16 8C16 3.58875 12.4113 0 8 0Z" fill="#003DA5"/>'
    + '<path d="M2.84668 14.1139C4.23975 15.2899 6.03821 15.9999 7.99976 15.9999C9.9613 15.9999 11.7598 15.2898 13.1528 14.1139C13.0245 12.9484 12.5007 11.8557 11.6659 11.0209C10.6864 10.0414 9.3844 9.50195 7.99976 9.50195C5.36255 9.50195 3.13293 11.5138 2.84668 14.1139Z" fill="#003DA5"/></svg>';

  function svg(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
      + 'stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || "") + '</svg>';
  }

  function topLink(id, label, href, icon, badge, active) {
    var cls = "side-link" + (id === active ? " is-active" : "");
    return '<a class="' + cls + '" href="' + href + '">' + svg(icon) + "<span>" + label + "</span>"
      + (badge ? '<span class="badge">' + badge + "</span>" : "") + "</a>";
  }

  function subLink(label, href, isActive) {
    return '<a class="side-sublink' + (isActive ? " is-active" : "") + '" href="' + href + '">'
      + '<span class="side-dot"></span><span>' + label + "</span></a>";
  }

  function wireMobileSidebar() {
    var sidebar = document.getElementById("app-sidebar");
    if (!sidebar || document.getElementById("sidebar-toggle")) return;

    var btn = document.createElement("button");
    btn.id = "sidebar-toggle";
    btn.className = "sidebar-toggle";
    btn.setAttribute("aria-label", "Open navigation menu");
    btn.setAttribute("aria-expanded", "false");
    btn.innerHTML = svg("chev") + "<span>Menu</span>";

    var backdrop = document.createElement("div");
    backdrop.className = "sidebar-backdrop";

    function setOpen(open) {
      sidebar.classList.toggle("is-open", open);
      backdrop.classList.toggle("is-open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    btn.addEventListener("click", function () { setOpen(!sidebar.classList.contains("is-open")); });
    backdrop.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
    window.addEventListener("resize", function () { if (window.innerWidth > 900) setOpen(false); });

    document.body.appendChild(btn);
    document.body.appendChild(backdrop);
  }

  function render() {
    var active = document.body.getAttribute("data-active") || "home";
    var activeId = document.body.getAttribute("data-active-id") || "";
    var html = "";

    html += '<div class="sidebar__brand">'
      + '<img src="./assets/logo.png" alt="P&G logo" />'
      + '<div class="brand-name">WHS GenAI<span>Data Agents Platform</span></div></div>';

    html += '<a class="btn btn--primary sidebar__new" href="index.html">+ New Thread</a>';

    html += '<nav class="sidebar__nav">';
    html += topLink("home", "Home", "index.html", "home", null, active);

    // ---- Workspace ----
    html += '<div class="sidebar__group-label">Workspace</div>';

    // Assistants (with nested workflow list)
    html += topLink("assistants", "Assistants", "assistants.html", "spark", String(W.assistants.length), active);
    html += '<div class="side-children">';
    W.assistants.forEach(function (a) {
      html += subLink(a.icon + "  " + a.name, "assistant.html?id=" + a.id, active === "assistants" && activeId === a.id);
    });
    html += "</div>";

    // Agents (with nested agent list)
    html += topLink("agents", "Agents", "agents.html", "agent", String(W.agents.length), active);
    html += '<div class="side-children">';
    W.agents.forEach(function (a) {
      html += subLink(a.icon + "  " + a.name, "agent.html?id=" + a.id, active === "agents" && activeId === a.id);
    });
    html += "</div>";

    // Skills
    html += topLink("skills", "Skills", "skills.html", "puzzle", String((W.skills || []).length), active);

    // ---- Knowledge ----
    html += '<div class="sidebar__group-label">Knowledge</div>';
    html += topLink("graph", "Semantic Layer & Knowledge Graph", "knowledge-graph.html", "graph", "live", active);
    html += topLink("data", "Warehouse Data & Knowledge", "data-knowledge.html", "data", null, active);

    html += "</nav>";

    var buildInfo = "";
    if (window.WHS_BUILD && window.WHS_BUILD.timestamp) {
      var okClass = window.WHS_BUILD.ok ? "text-success" : "text-danger";
      var okDot = window.WHS_BUILD.ok ? "#10b981" : "#ef4444";
      buildInfo = '<div style="padding:8px 12px;margin:10px 12px 4px;background:rgba(0,0,0,0.03);border-radius:8px;font-size:11px;color:#64748b;display:flex;align-items:center;gap:6px;">'
        + '<span style="width:7px;height:7px;border-radius:50%;background:' + okDot + ';display:inline-block;flex-none:1"></span>'
        + '<div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">Build: <b>' + window.WHS_BUILD.timestamp.split(" ")[0] + '</b></div>'
        + '</div>';
    }

    html += buildInfo;

    html += '<div class="sidebar__user"><span class="ds-avatar">' + AVATAR + "</span>"
      + '<div class="u-meta"><div class="u-name">Feng, Xiaobo</div><div class="u-role">OSS Warehousing</div></div></div>';

    var mount = document.getElementById("app-sidebar");
    if (mount) {
      mount.innerHTML = html;
      wireMobileSidebar();
    }
  }

  /* ---- Design-note block: input a note + save it into THIS html ---- */
  function mountDesignNote() {
    if (document.getElementById("design-note-fab")) return;
    var page = (location.pathname.split("/").pop() || "index.html");
    var key = "whs-design-note:" + page;
    var saved = "";
    try { saved = localStorage.getItem(key) || ""; } catch (e) {}
    var existing = document.getElementById("page-design-note");
    if (existing && !saved) saved = existing.getAttribute("data-note") || "";

    var fab = document.createElement("button");
    fab.id = "design-note-fab";
    fab.className = "dn-fab";
    fab.title = "Design notes for this page";
    fab.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg><span>Design</span>';

    var panel = document.createElement("div");
    panel.id = "design-note-panel";
    panel.className = "dn-panel";
    panel.innerHTML =
      '<div class="dn-panel__head"><strong>Design notes</strong><span class="dn-panel__page">' + page + '</span>'
      + '<button class="dn-x" title="Close">&times;</button></div>'
      + '<textarea id="dn-text" placeholder="Write your design note for this page…"></textarea>'
      + '<div class="dn-actions"><span class="dn-status" id="dn-status"></span>'
      + '<button class="btn btn--outline btn--sm" id="dn-save">Save</button>'
      + '<button class="btn btn--primary btn--sm" id="dn-download">Save into HTML</button></div>';

    document.body.appendChild(fab);
    document.body.appendChild(panel);
    var ta = panel.querySelector("#dn-text");
    ta.value = saved;

    fab.onclick = function () { panel.classList.toggle("is-open"); if (panel.classList.contains("is-open")) ta.focus(); };
    panel.querySelector(".dn-x").onclick = function () { panel.classList.remove("is-open"); };
    panel.querySelector("#dn-save").onclick = function () {
      try { localStorage.setItem(key, ta.value); } catch (e) {}
      var s = document.getElementById("dn-status"); s.textContent = "Saved locally"; setTimeout(function(){s.textContent="";}, 2000);
    };
    panel.querySelector("#dn-download").onclick = function () {
      try { localStorage.setItem(key, ta.value); } catch (e) {}
      var note = ta.value.replace(/<\/?script/gi, "");
      var block = '<div id="page-design-note" data-note="' + note.replace(/"/g, "&quot;") + '" style="max-width:1100px;margin:24px auto;padding:16px 20px;border:1px solid #d6dae0;border-radius:12px;background:#f7f9fc"><strong>Design notes</strong><pre style="white-space:pre-wrap;font-family:inherit;margin:8px 0 0">' + note.replace(/</g,"&lt;") + '</pre></div>';
      var doc = "<!DOCTYPE html>\n" + document.documentElement.outerHTML;
      doc = doc.replace(/<div id="page-design-note"[\s\S]*?<\/div>\s*<\/div>/, "");
      doc = doc.replace(/<\/main>/, block + "</main>");
      var blob = new Blob([doc], { type: "text/html" });
      var a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = page;
      document.body.appendChild(a); a.click(); a.remove();
      var s = document.getElementById("dn-status"); s.textContent = "Downloaded — replace the file to save"; setTimeout(function(){s.textContent="";}, 4000);
    };
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { render(); mountDesignNote(); });
  else { render(); mountDesignNote(); }
})();
