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
      if (!document.querySelector(".p21-key") || a.dataset.nav === "start" || a.dataset.nav === "finish" || a.dataset.empty) {
        if (dot) dot.className = "p21-dot p21-none";
        return;
      }
      var n = missingIn(a);
      a.dataset.state = n ? "missing" : "ok";
      if (dot) { dot.className = n ? "p21-miss" : "p21-ok"; dot.textContent = n ? String(n) : "✓"; }
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
