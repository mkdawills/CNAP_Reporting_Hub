/* Screen 21 prototype: the section navigator (MW 2026-11-05).
   Read-only helper: it never changes answers or submits anything.
   - Highlights the section you are reading.
   - Shows, per section, how many required answers are still empty, or a check mark.
     The server still checks every required answer when you press Submit. */
(function () {
  var nav = document.querySelector(".p21-nav");
  if (!nav) return;
  var links = Array.from(nav.querySelectorAll("a[data-nav]"));

  function questionsIn(sec) {
    return Array.from(sec.querySelectorAll(".q, .repeat")).filter(function (q) { return !q.closest("[hidden]"); });
  }
  function answered(q) {
    var radios = q.querySelectorAll("input[type=radio]");
    if (radios.length) return Array.from(radios).some(function (r) { return r.checked; });
    var file = q.querySelector("input[type=file]");
    if (file) return (file.files && file.files.length > 0) || !!q.querySelector(".filename");
    var fields = Array.from(q.querySelectorAll("input[type=text], input[type=number], input[type=date], input[type=email], textarea, select"));
    if (!fields.length) return null;
    return fields.some(function (f) { return String(f.value || "").trim() !== ""; });
  }
  // Markers (MW 2026-11-05, option B): how many required answers in each section are still empty.
  // A question is required when the form marks it so; the server re-checks everything on Submit.
  function missingIn(a) {
    var codes = (a.dataset.req || "").trim().split(/\s+/).filter(Boolean);
    return codes.filter(function (c) {
      var q = document.getElementById("q-" + c);
      if (!q || q.closest("[hidden]")) return false;
      return answered(q) === false;
    }).length;
  }
  // The Word document covers Accomplishments, Plans, and Changes together (MW 2026-11-05), so those
  // outline parts share one marker: the required answers across all of them.
  var partLinks = links.filter(function (a) { return a.dataset.part; });
  var partReq = partLinks.map(function (a) { return a.dataset.req || ""; }).join(" ");
  partLinks.forEach(function (a) { a.dataset.req = partReq; a.dataset.shared = "1"; });
  function refresh() {
    links.forEach(function (a) {
      var dot = a.querySelector(".p21-dot, .p21-miss, .p21-ok");
      var sr = a.querySelector(".p21-navstate");
      // Sections with nothing to answer (the outline parts of the Word document, the intro, the end)
      // show no marker, so a check mark never suggests work is done when there was nothing to do.
      // Counts of missing answers mean something only while the form can still be filled in.
      if (!document.querySelector(".p21-nav[data-editable]") || a.dataset.nav === "start" || a.dataset.nav === "finish" || a.dataset.empty) {
        if (dot) dot.className = "p21-dot p21-none";
        return;
      }
      // Optional sections show no marker until something is typed in them, so an empty
      // section never looks finished (MW 2026-11-05).
      if (!(a.dataset.req || "").trim()) {
        var sec = document.querySelector(a.getAttribute("href"));
        var typed = sec && Array.prototype.some.call(sec.querySelectorAll("textarea, input[type=text], input[type=number], input[type=date], select, input[type=radio]:checked, input[type=checkbox]:checked"), function (el) {
          return (el.type === "radio" || el.type === "checkbox") ? true : (el.value || "").trim() !== "";
        });
        if (!typed) {
          if (dot) { dot.className = "p21-dot p21-none"; dot.textContent = ""; }
          var mt0 = dot && dot.nextElementSibling && dot.nextElementSibling.querySelector(".p21-misstext");
          if (mt0) mt0.hidden = true;
          a.dataset.state = "";
          if (sr) sr.textContent = " (Optional)";
          a.title = "Optional";
          return;
        }
      }
      var n = missingIn(a);
      a.dataset.state = n ? "missing" : "ok";
      // The words sit in the list itself ("3 missing"), so no key is needed (MW 2026-11-05).
      if (dot) { dot.className = n ? "p21-miss" : "p21-ok"; dot.textContent = n ? "" : "✓"; }
      var label = dot && dot.nextElementSibling;
      if (label) {
        var mt = label.querySelector(".p21-misstext");
        if (!mt) { mt = document.createElement("span"); mt.className = "p21-misstext"; mt.setAttribute("aria-hidden", "true"); label.appendChild(mt); }
        mt.textContent = !n ? "" : (a.dataset.shared ? "Word document missing" : n + " missing");
        mt.hidden = !n;
      }
      var words = n ? n + " required answer" + (n === 1 ? "" : "s") + " still missing" : "Nothing required is missing";
      if (a.dataset.shared) words += n ? ": the Word document covering Accomplishments, Plans, and Changes" : ": the Word document is uploaded";
      if (sr) sr.textContent = " (" + words + ")";
      a.title = words;
    });
  }
  refresh();
  document.addEventListener("input", refresh);
  document.addEventListener("change", refresh);

  if ("IntersectionObserver" in window) {
    var targets = links.map(function (a) { return document.querySelector(a.getAttribute("href")); }).filter(Boolean);
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        var id = "#" + e.target.id;
        links.forEach(function (a) {
          var on = a.getAttribute("href") === id;
          a.classList.toggle("on", on);
          if (on) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
        });
      });
    }, { rootMargin: "-20% 0px -70% 0px" });
    targets.forEach(function (t) { io.observe(t); });
  }
  var miss = document.getElementById("p21-missing");
  if (miss) miss.focus();
})();

/* Screen 53 prototype: in "People and their forms", each person's name shows once, at the top of
   their group of rows. Re-checked after any sort, so names never go missing. Screen readers still
   hear the name on every row. */
(function () {
  var table = document.querySelector("table.d53-people");
  if (!table) return;
  function group() {
    var prev = null;
    Array.from(table.tBodies[0].rows).forEach(function (r) {
      var th = r.querySelector("th[data-person]"); if (!th) return;
      var same = th.dataset.person === prev;
      r.classList.toggle("d53-same", same); r.classList.toggle("d53-first", !same);
      prev = th.dataset.person;
    });
  }
  group();
  table.addEventListener("click", function () { setTimeout(group, 0); });
})();

/* Roll-ups (MW 2026-11-05): Show all / Collapse all for each group of rolled-up sections, and a
   link to anything inside a rolled-up section opens that section first. */
(function () {
  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-roll]");
    if (!b) return;
    var group = b.closest("[data-rollgroup]");
    if (!group) return;
    group.querySelectorAll(":scope details.px-roll").forEach(function (d) {
      if (d.parentElement.closest("details.px-roll") && group.contains(d.parentElement.closest("details.px-roll"))) return;
      d.open = b.dataset.roll === "open";
    });
  });
  function reveal(id) {
    var t = id && document.getElementById(id);
    for (var d = t && t.closest("details"); d; d = d.parentElement.closest("details")) d.open = true;
    if (t) t.scrollIntoView();
  }
  if (location.hash) reveal(decodeURIComponent(location.hash.slice(1)));
  document.addEventListener("click", function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (a && a.getAttribute("href").length > 1) reveal(a.getAttribute("href").slice(1));
  });
})();

/* "On this page": highlight the section being read. */
(function () {
  var links = Array.from(document.querySelectorAll(".px-onpage a[data-onpage]"));
  if (!links.length || !("IntersectionObserver" in window)) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var id = "#" + e.target.id;
      links.forEach(function (a) {
        var on = a.getAttribute("href") === id;
        a.classList.toggle("on", on);
        if (on) a.setAttribute("aria-current", "location"); else a.removeAttribute("aria-current");
      });
    });
  }, { rootMargin: "-15% 0px -75% 0px" });
  links.forEach(function (a) { var t = document.querySelector(a.getAttribute("href")); if (t) io.observe(t); });
})();

/* Hover descriptions for the section lists. */
document.querySelectorAll(".px-onpage a[data-onpage], .p21-nav a[data-nav]").forEach(function (a) {
  if (a.title) return;
  var t = a.textContent.replace(/\s+/g, " ").trim();
  a.title = "Jump to " + t + ". A rolled-up section opens.";
});

/* Screen 90: Show all opens every part and section; Collapse all leaves only the numbered parts. */
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest("[data-pageroll]");
  if (!b) return;
  var open = b.dataset.pageroll === "open";
  var main = b.closest(".px-onpage-main") || document;
  main.querySelectorAll("details.r90-partroll").forEach(function (d) { d.open = open; });
  if (open) main.querySelectorAll("details.px-roll").forEach(function (d) { d.open = true; });
});

/* Prototype screen 5: the role box opens only when "Other" is chosen (MW: every Other opens a text box). */
(function () {
  function sync(sel) {
    var box = sel.closest("form").querySelector("[data-other-sel-box]");
    if (box) box.hidden = sel.value !== "other";
  }
  document.querySelectorAll("select[data-role]").forEach(sync);
  document.addEventListener("change", function (e) { if (e.target.matches && e.target.matches("select[data-role]")) sync(e.target); });
})();

/* Screen 21: the section list can collapse to a slim strip on the left (MW 2026-11-05).
   The choice is remembered in this browser only. */
(function () {
  var nav = document.getElementById("p21-nav");
  var btn = nav && nav.querySelector("[data-navtoggle]");
  if (!btn) return;
  var layout = nav.closest(".p21-layout");
  function set(closed, save) {
    layout.classList.toggle("navclosed", closed);
    btn.setAttribute("aria-expanded", String(!closed));
    btn.querySelector(".p21-cw").textContent = closed ? "Show" : "Hide";
    btn.title = closed ? "Show the list of sections again." : "Hide this list to give the form more room. You can bring it back any time.";
    if (save) { try { localStorage.setItem("px-nav-closed", closed ? "1" : "0"); } catch (e) {} }
  }
  var saved = null;
  try { saved = localStorage.getItem("px-nav-closed"); } catch (e) {}
  set(saved === "1", false);
  btn.addEventListener("click", function () { set(!layout.classList.contains("navclosed"), true); });
})();

/* "On this page" Hide on every long page (MW 2026-11-05, option A). One remembered choice for all pages. */
(function () {
  document.querySelectorAll(".px-onpage [data-navtoggle]").forEach(function (btn) {
    var layout = btn.closest(".px-onpage-layout");
    if (!layout) return;
    function set(closed, save) {
      layout.classList.toggle("navclosed", closed);
      btn.setAttribute("aria-expanded", String(!closed));
      btn.querySelector(".p21-cw").textContent = closed ? "Show" : "Hide";
      btn.title = closed ? "Show the list of sections again." : "Hide this list to give the page more room. You can bring it back any time.";
      if (save) { try { localStorage.setItem("px-nav-closed", closed ? "1" : "0"); } catch (e) {} }
    }
    var saved = null;
    try { saved = localStorage.getItem("px-nav-closed"); } catch (e) {}
    set(saved === "1", false);
    btn.addEventListener("click", function () { set(!layout.classList.contains("navclosed"), true); });
  });
})();

/* At the end of a form, the Review and submit section has both buttons, so the bottom bar's
   copies step aside and only the save status stays (MW 2026-11-05). */
(function () {
  var fin = document.getElementById("p21-finish"), bar = document.querySelector(".p21-bar");
  if (!fin || !bar || !("IntersectionObserver" in window)) return;
  new IntersectionObserver(function (es) {
    bar.classList.toggle("at-end", es[0].isIntersecting);
  }, { threshold: 0.25 }).observe(fin);
})();

/* Stacked sentences: a little space between each one, everywhere (MW 2026-11-05). */
(function () {
  var skip = "button, .px-btn, .px-chip, th, .px-label, .p21-bar, select, option, svg, pre, .si-photo";
  function gap(root) {
    (root || document).querySelectorAll("br").forEach(function (br) {
      if (br.closest(skip)) return;
      var n = br.nextSibling;
      if (n && n.nodeType === 1 && n.classList.contains("sgap")) return;
      while (n && n.nodeType === 3 && !n.textContent.trim()) n = n.nextSibling;
      if (!n) return; /* a break at the very end adds nothing */
      var s = document.createElement("span");
      s.className = "sgap";
      s.setAttribute("aria-hidden", "true");
      br.after(s);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { gap(); });
  else gap();
  window.pxGap = gap;
})();

/* Grant-year picker (MW 2026-11-06): "All years" ticks every year; unticking a year unticks "All years". */
(function () {
  var f = document.getElementById("r33-years");
  if (!f) return;
  var all = f.querySelector("[data-allyears]"), ys = f.querySelectorAll("[data-year]");
  if (all) all.addEventListener("change", function () { ys.forEach(function (y) { y.checked = all.checked; }); });
  ys.forEach(function (y) { y.addEventListener("change", function () { if (all) all.checked = Array.prototype.every.call(ys, function (x) { return x.checked; }); }); });
  f.addEventListener("submit", function () { if (all && all.checked) ys.forEach(function (y) { y.disabled = true; }); });
})();

/* Administration pages (Batch 3, MW 2026-11-06; checklist B, E, J). Runs after the page's own
   roll-up scripts. It only moves and labels existing links and sections; every link keeps its address.
   - Tabs sit at the top of the white page, as on Center results.
   - Every file download moves into one Download menu at the bottom, with Excel beside CSV.
   - Every rolled-up section says Show or Hide with an arrow, as on the approved screens. */
(function () {
  if (!document.body.classList.contains("pa")) return;
  function run() {
    var page = document.querySelector(".pa-page");
    if (!page) return;
    // Tabs first.
    var tabs = page.querySelector(".tabs");
    if (tabs && !tabs.closest("details")) {
      var keep = tabs.querySelectorAll("a.tabdl:not(.tabdl2)");
      page.insertBefore(tabs, page.firstChild);
      if (keep.length) {
        var line = document.createElement("p"); line.className = "pa-tablinks";
        keep.forEach(function (a) { line.appendChild(a); });
        tabs.after(line);
      }
    }
    // Downloads to the bottom menu.
    var NAMES = { pubs: "Publications list", publications: "Publications list", grants: "Grant proposals list", talks: "Presentations list",
      presentations: "Presentations list", counts: "Counts", c1: "RPPR C.1: publications", table1: "RPPR Tables 1A and 1B",
      table2: "RPPR Table 2", d1: "RPPR D.1: participants", nihdocs: "NIH documents, every file", teams: "Research teams",
      sitevisit: "Site-visit tables and item lists" };
    var rows = [];
    Array.prototype.forEach.call(page.querySelectorAll("a[href]"), function (a) {
      var t = a.textContent.trim();
      if (!/^Download\b/.test(t) || !/\((CSV|zip)\)$/i.test(t) || a.closest("form, .sheetup, .px-dl")) return;
      var href = a.getAttribute("href"), m = href.match(/\/outcomes\/export\/([\w-]+)\//), kind = m && m[1];
      var label = (kind && NAMES[kind]) || t.replace(/^Download\s+/, "").replace(/\s*\((CSV|zip)\)$/i, "");
      label = label.charAt(0).toUpperCase() + label.slice(1);
      var fmts = [];
      if (/\(zip\)$/i.test(t)) fmts.push(["Zip", href]);
      else {
        var xl = (m || /\/results\/.+\/export\//.test(href)) ? href + (href.indexOf("?") > -1 ? "&" : "?") + "format=xlsx" : null;
        if (xl) fmts.push(["Excel", xl]);
        fmts.push(["CSV", href]);
      }
      rows.push([label, fmts, a.title || ""]);
      var host = a.parentElement; a.remove();
      if (host && host !== page && !host.textContent.replace(/[\s·]/g, "") && !host.querySelector("a, button, input, select")) host.remove();
    });
    if (rows.length) {
      var ic = '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3v9m0 0-3.5-3.5M10 12l3.5-3.5M4 15.5h12"/></svg>';
      var cue = '<svg class="px-dl-cue" viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l5-5 5 5"/></svg>';
      var foot = document.createElement("div"); foot.className = "px-dlfoot";
      var html = '<details class="px-dl"><summary title="Every download on this page, each with its formats.">' + ic + "<span>Download</span>" + cue + '</summary><div class="px-dl-menu" role="group" aria-label="Downloads">';
      rows.forEach(function (r) {
        html += '<div class="px-dl-row"><span></span><span>' + r[1].map(function (f) { return '<a class="px-link" href="' + f[1].replace(/"/g, "&quot;") + '"></a>'; }).join(" ") + "</span></div>";
      });
      foot.innerHTML = html + "</div></details>";
      Array.prototype.forEach.call(foot.querySelectorAll(".px-dl-row"), function (row, i) {
        row.firstChild.textContent = rows[i][0];
        Array.prototype.forEach.call(row.querySelectorAll("a"), function (a, j) {
          var f = rows[i][1][j]; a.textContent = f[0];
          a.title = "Downloads " + rows[i][0].charAt(0).toLowerCase() + rows[i][0].slice(1) + (f[0] === "Excel" ? " as an Excel workbook." : f[0] === "CSV" ? " as a CSV file that opens in Excel." : " as one zip file.");
        });
      });
      page.appendChild(foot);
    }
    // Show or Hide on every rolled-up section.
    Array.prototype.forEach.call(page.querySelectorAll("details > summary"), function (s) {
      if (!(s.querySelector("h2, h3, .sectionhead") || s.parentElement.classList.contains("lgroup")) || s.querySelector(".px-roll-cue")) return;
      s.parentElement.classList.add("pa-roll");
      var c = document.createElement("span"); c.className = "px-roll-cue"; c.setAttribute("aria-hidden", "true"); s.appendChild(c);
    });
    Array.prototype.forEach.call(page.querySelectorAll(".rollhead"), function (h) {
      if (h.querySelector(".px-roll-cue")) return;
      var c = document.createElement("span"); c.className = "px-roll-cue"; c.setAttribute("aria-hidden", "true"); h.appendChild(c);
    });
    // One Show all and Collapse all per page (checklist 38): later copies drive every section on the page instead of repeating.
    var bars = page.querySelectorAll(".foldall:not(.taskfold)");
    if (bars.length > 1) {
      var first = bars[0], rest = Array.prototype.slice.call(bars, 1);
      var btns = first.querySelectorAll("button");
      btns[0].addEventListener("click", function () { rest.forEach(function (b) { b.querySelectorAll("button")[0].click(); }); });
      btns[1].addEventListener("click", function () { rest.forEach(function (b) { b.querySelectorAll("button")[1].click(); }); });
      rest.forEach(function (b) { b.hidden = true; });
    }
  }
  document.addEventListener("DOMContentLoaded", function () { setTimeout(run, 0); });
})();

/* Confirm on the page (MW 2026-11-06, checklist 110). Closing a period, finalizing, launching, sending email,
   and removing something ask first, in a short note under the button, instead of the browser's gray pop-up.
   The note names what will happen; "Yes, ..." does exactly what the button always did. */
(function () {
  function msgOf(code) {
    var m = /confirm\(\s*'((?:[^'\\]|\\.)*)'\s*\)/.exec(code || "");
    if (!m) return null;
    try { return JSON.parse('"' + m[1].replace(/\\'/g, "'").replace(/"/g, '\\"') + '"'); } catch (e) { return m[1]; }
  }
  function setup() {
    document.querySelectorAll("[onclick*='confirm(']").forEach(function (b) {
      var t = msgOf(b.getAttribute("onclick")); if (t === null) return;
      b.removeAttribute("onclick"); b.setAttribute("data-confirm", t);
    });
    document.querySelectorAll("form[onsubmit*='confirm(']").forEach(function (f) {
      var t = msgOf(f.getAttribute("onsubmit")); if (t === null) return;
      f.removeAttribute("onsubmit"); f.setAttribute("data-confirm", t);
    });
  }
  function close(panel, back) { if (panel) { panel.remove(); if (back) { back.hidden = false; back.focus(); } } }
  function ask(form, btn, text) {
    var old = form.parentNode.querySelector(":scope > .px-confirm"); if (old) { old.remove(); form.querySelectorAll("[hidden][data-confirm]").forEach(function (x) { x.hidden = false; }); }
    var label = (btn && btn.textContent.trim()) || "Continue";
    var yesText = (btn && btn.getAttribute("data-yes")) || "Yes, " + (/^[A-Z]{2}/.test(label) ? label : label.charAt(0).toLowerCase() + label.slice(1));
    var p = document.createElement("div"); p.className = "px-callout px-confirm"; p.setAttribute("role", "alertdialog"); p.setAttribute("aria-live", "assertive");
    /* The approved message style: the question in bold, each further sentence on its own line. */
    text.split(/(?<=[.?!])\s+/).forEach(function (s, i) { var q = document.createElement("p"); if (i === 0) { var st = document.createElement("strong"); st.textContent = s; q.appendChild(st); } else q.textContent = s; p.appendChild(q); });
    /* One action at a time: the original button steps aside while the note is open (checklist 51). */
    if (btn) btn.hidden = true;
    var row = document.createElement("div"); row.className = "px-confirm-row";
    var yes = document.createElement("button"); yes.type = "button"; yes.className = "btn px-btn"; yes.textContent = yesText; yes.title = "Goes ahead: " + label.toLowerCase() + ".";
    var no = document.createElement("button"); no.type = "button"; no.className = "btn ghost px-btn px-btn-ghost"; no.textContent = "No, go back"; no.title = "Closes this note. Nothing changes.";
    row.appendChild(yes); row.appendChild(no); p.appendChild(row);
    form.after(p); yes.focus();
    yes.addEventListener("click", function () { form.dataset.ok = "1"; if (btn) btn.dataset.ok = "1"; p.remove(); if (form.requestSubmit) form.requestSubmit(btn || undefined); else (btn || form).click(); });
    no.addEventListener("click", function () { close(p, btn); });
    p.addEventListener("keydown", function (e) { if (e.key === "Escape") close(p, btn); });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("button[data-confirm], input[type=submit][data-confirm]");
    if (!b || !document.body.classList.contains("proto")) return;
    if (b.dataset.ok === "1") { delete b.dataset.ok; return; }
    var f = b.form; if (!f) return;
    e.preventDefault(); ask(f, b, b.getAttribute("data-confirm"));
  }, true);
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (!document.body.classList.contains("proto") || !f.hasAttribute("data-confirm")) return;
    if (f.dataset.ok === "1") { delete f.dataset.ok; return; }
    e.preventDefault(); ask(f, e.submitter || f.querySelector("[type=submit], button:not([type=button])"), f.getAttribute("data-confirm"));
  }, true);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
})();

/* Reporting periods (MW 2026-11-06, "more mental clarity regarding division"): each period reads top to bottom as
   its name, where it stands on the step line, its dates, the next step with its button, then its quiet links. */
(function () {
  if (!document.body.classList.contains("pa")) return;
  document.querySelectorAll(".pcard").forEach(function (card) {
    var head = card.querySelector(":scope > .head"), life = card.querySelector(":scope > ol.life");
    if (!head || !life) return;
    var h2 = head.querySelector("h2");
    if (h2) h2.after(life);
    var tl = card.querySelector(":scope > details.px-tl"); if (tl) life.after(tl);
    card.querySelectorAll(":scope > p.small").forEach(function (p) { if (p.querySelector("a")) { p.classList.add("pa-cardlinks"); head.after(p); } });
  });
})();
