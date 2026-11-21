/* =====================================================================
   WHS GenAI — Q&A Bot widget
   Injects a floating assistant on every page. Answers are grounded in
   the M&M workspace knowledge base (window.WHS.answer / botKB).
  Prototype-only: no network calls.
   ===================================================================== */
(function () {
  var W = window.WHS;

  var SUGGESTIONS = [
    "How does RTCIS → PrIME remediation work?",
    "Which sites are validated?",
    "What are the 4 agents?",
    "What is the IRA timeout fix?",
    "FP vs RPM?",
    "What is the ontology?"
  ];

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmt(s) {
    // very light markdown: **bold**
    return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function build() {
    var fab = document.createElement("button");
    fab.className = "bot-fab";
    fab.title = "Ask the WHS assistant";
    fab.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';

    var panel = document.createElement("div");
    panel.className = "bot-panel";
    panel.innerHTML =
      '<div class="bot-head">'
      + '<span class="ds-avatar"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg></span>'
      + '<div><div class="bot-title">WHS Assistant</div><div class="bot-sub">Grounded in the M&amp;M workspace</div></div>'
      + '<button class="bot-close" title="Close">&times;</button>'
      + '</div>'
      + '<div class="bot-msgs" id="bot-msgs"></div>'
      + '<div class="bot-suggest" id="bot-suggest"></div>'
      + '<div class="bot-input"><input id="bot-text" placeholder="Ask about flows, sites, agents…" />'
      + '<button id="bot-send" title="Send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg></button></div>';

    document.body.appendChild(fab);
    document.body.appendChild(panel);

    var msgs = panel.querySelector("#bot-msgs");
    var suggest = panel.querySelector("#bot-suggest");
    var input = panel.querySelector("#bot-text");

    function add(role, text) {
      var d = document.createElement("div");
      d.className = "bot-msg " + role;
      d.innerHTML = fmt(text);
      msgs.appendChild(d);
      msgs.scrollTop = msgs.scrollHeight;
    }

    function addAnswer(q) {
      var r = (W && W.answerRich) ? W.answerRich(q) : { a: (W && W.answer ? W.answer(q) : "Knowledge base not loaded."), sources: [] };
      var d = document.createElement("div");
      d.className = "bot-msg bot";
      var nSrc = (r.sources && r.sources.length) || 0;
      d.innerHTML = fmt(r.a)
        + '<a class="bot-more" href="answer.html?q=' + encodeURIComponent(q) + '">'
        + 'Open full answer' + (nSrc ? ' · ' + nSrc + ' source' + (nSrc === 1 ? "" : "s") : "") + ' &#8594;</a>';
      msgs.appendChild(d);
      msgs.scrollTop = msgs.scrollHeight;
    }

    function send(text) {
      text = (text || input.value).trim();
      if (!text) return;
      add("user", text);
      input.value = "";
      setTimeout(function () { addAnswer(text); }, 220);
    }

    SUGGESTIONS.forEach(function (s) {
      var c = document.createElement("button");
      c.className = "bot-chip";
      c.textContent = s;
      c.onclick = function () { send(s); };
      suggest.appendChild(c);
    });

    add("bot", "Hi Xiaobo — ask me anything about the WHS GenAI workspace: Warehouse Natural Language Query, SQL Remediation, Process Discovery, the Knowledge Graph, agents, or any registered site.");

    fab.onclick = function () { panel.classList.toggle("is-open"); if (panel.classList.contains("is-open")) input.focus(); };
    panel.querySelector(".bot-close").onclick = function () { panel.classList.remove("is-open"); };
    panel.querySelector("#bot-send").onclick = function () { send(); };
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") send(); });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})();
