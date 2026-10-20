// CPG Europe Daily — search, section filters, theme toggle.
// Pages work without this script; it only adds interactivity.
(function () {
  "use strict";
  var root = document.body.dataset.root || "";
  var q = document.getElementById("q");
  var scopeBox = document.getElementById("scope-all");
  var edition = document.getElementById("edition");
  var results = document.getElementById("results");
  var nomatch = document.getElementById("nomatch");
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var cards = Array.prototype.slice.call(document.querySelectorAll("#edition .card"));
  var sections = Array.prototype.slice.call(document.querySelectorAll("#edition .section[data-section]"));
  var archiveOnly = q && q.dataset.scope === "all";
  var filter = "all";
  var index = null, indexLoading = null;

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c];
    });
  }
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function tokens() {
    return (q ? q.value : "").toLowerCase().trim().split(/\s+/).filter(Boolean);
  }
  function matches(text, toks) {
    for (var i = 0; i < toks.length; i++) if (text.indexOf(toks[i]) < 0) return false;
    return true;
  }
  function highlight(text, toks) {
    if (!toks.length) return esc(text);
    var rx = new RegExp("(" + toks.map(function (t) {
      return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|") + ")", "gi");
    // Odd-numbered parts are the matched terms
    return String(text || "").split(rx).map(function (part, i) {
      return i % 2 ? "<mark>" + esc(part) + "</mark>" : esc(part);
    }).join("");
  }
  function searchAll() { return archiveOnly || (scopeBox && scopeBox.checked); }

  // ---- filtering this edition ----
  cards.forEach(function (c) {
    var a = c.querySelector("h3 a");
    c._title = a ? a.textContent : "";
    c._link = a;
  });

  function filterEdition(toks) {
    var visible = 0;
    cards.forEach(function (c) {
      var inTop = c.closest("[data-section]").dataset.section === "top";
      var okFilter = filter === "all" || (filter === "top" ? inTop : c.dataset.cat === filter);
      var show = okFilter && matches(c.dataset.text, toks);
      c.hidden = !show;
      if (show) visible++;
      if (c._link) c._link.innerHTML = highlight(c._title, toks);
    });
    sections.forEach(function (s) {
      s.hidden = !s.querySelector(".card:not([hidden])");
    });
    if (nomatch) nomatch.hidden = visible > 0 || !cards.length;
  }

  // ---- searching every edition ----
  function loadIndex() {
    if (index) return Promise.resolve(index);
    if (!indexLoading) {
      indexLoading = fetch(root + "search-index.json")
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
        .then(function (rows) {
          rows.forEach(function (r) { r._text = (r.t + " " + r.s + " " + r.src).toLowerCase(); });
          index = rows;
          return rows;
        });
    }
    return indexLoading;
  }

  function prettyDate(d) {
    var dt = new Date(d + "T12:00:00Z");
    return dt.toLocaleDateString("en-GB", {weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC"});
  }

  function renderResults(toks) {
    results.hidden = false;
    edition.hidden = true;
    results.innerHTML = '<p class="results__head">Searching…</p>';
    loadIndex().then(function (rows) {
      if (toks.join(" ") !== tokens().join(" ")) return; // stale
      var catFilter = filter !== "all" && filter !== "top" ? filter : null;
      var hits = rows.filter(function (r) {
        return matches(r._text, toks) && (!catFilter || slug(r.c) === catFilter);
      });
      var limit = 150, html = [], day = null;
      html.push('<div class="results__head"><span><b>' + hits.length + "</b> stor" +
        (hits.length === 1 ? "y" : "ies") + " across all editions" +
        (hits.length > limit ? " — showing the newest " + limit : "") + "</span>" +
        '<button type="button" class="linkbtn" id="clear-search">Clear search</button></div>');
      hits.slice(0, limit).forEach(function (r) {
        if (r.d !== day) {
          day = r.d;
          html.push('<h3 class="results__day"><a href="' + root + "archive/" + r.d + '.html">' +
            esc(prettyDate(r.d)) + "</a></h3>");
        }
        var cat = slug(r.c);
        html.push('<article class="card" data-cat="' + cat + '"><span class="pill pill--' + cat + '">' +
          esc(r.c) + '</span><h3><a href="' + esc(r.l) + '" target="_blank" rel="noopener">' +
          highlight(r.t, toks) + "</a></h3><p>" + highlight(r.s, toks) +
          '</p><div class="meta"><b>' + esc(r.src) + "</b></div></article>");
      });
      if (!hits.length) html.push('<div class="empty">No stories match “' + esc(q.value) + '”.</div>');
      results.innerHTML = html.join("");
      var clear = document.getElementById("clear-search");
      if (clear) clear.addEventListener("click", function () { q.value = ""; update(); q.focus(); });
    }).catch(function () {
      results.innerHTML = '<div class="empty">Search index could not be loaded.</div>';
    });
  }

  // ---- state & URL ----
  function syncUrl() {
    var p = new URLSearchParams();
    if (q && q.value.trim()) p.set("q", q.value.trim());
    if (scopeBox && scopeBox.checked) p.set("all", "1");
    if (filter !== "all") p.set("section", filter);
    var s = p.toString();
    history.replaceState(null, "", location.pathname + (s ? "?" + s : "") + location.hash);
  }

  function update() {
    var toks = tokens();
    if (searchAll() && toks.length) {
      renderResults(toks);
    } else {
      results.hidden = true;
      edition.hidden = false;
      filterEdition(toks);
    }
    syncUrl();
  }

  var timer;
  if (q) {
    q.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(update, 120); });
    q.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { q.value = ""; update(); q.blur(); }
    });
  }
  if (scopeBox) scopeBox.addEventListener("change", update);
  var allBtn = document.getElementById("search-all-btn");
  if (allBtn && scopeBox) allBtn.addEventListener("click", function () { scopeBox.checked = true; update(); });

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      filter = chip.dataset.filter;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c === chip)); });
      update();
    });
  });

  document.addEventListener("keydown", function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || "";
    if (e.key === "/" && q && tag !== "INPUT" && tag !== "TEXTAREA") {
      e.preventDefault();
      q.focus();
      q.select();
    }
  });

  // Restore state from the URL (?q=…&all=1&section=…)
  var params = new URLSearchParams(location.search);
  if (q && params.get("q")) q.value = params.get("q");
  if (scopeBox && params.get("all") === "1") scopeBox.checked = true;
  var sec = params.get("section");
  chips.forEach(function (c) { if (c.dataset.filter === sec) { filter = sec; } });
  chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c.dataset.filter === filter)); });
  if (q && (q.value || filter !== "all")) update();

  // ---- theme toggle ----
  var toggle = document.querySelector(".theme-toggle");
  if (toggle) toggle.addEventListener("click", function () {
    var el = document.documentElement;
    var dark = el.dataset.theme ? el.dataset.theme === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    el.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("theme", el.dataset.theme); } catch (e) {}
  });

  // ---- back to top ----
  var top = document.querySelector(".totop");
  if (top) {
    window.addEventListener("scroll", function () {
      top.classList.toggle("show", window.scrollY > 700);
    }, {passive: true});
    top.addEventListener("click", function (e) { e.preventDefault(); window.scrollTo(0, 0); });
  }
})();
