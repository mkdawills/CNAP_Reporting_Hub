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
  function refresh() {
    links.forEach(function (a) {
      var dot = a.querySelector(".p21-dot, .p21-miss, .p21-ok");
      var sr = a.querySelector(".p21-navstate");
      if (a.dataset.nav === "start" || a.dataset.nav === "finish") {
        if (dot) dot.className = "p21-dot p21-none";
        return;
      }
      var n = missingIn(a);
      a.dataset.state = n ? "missing" : "ok";
      if (dot) { dot.className = n ? "p21-miss" : "p21-ok"; dot.textContent = n ? String(n) : "✓"; }
      var words = n ? n + " required answer" + (n === 1 ? "" : "s") + " still missing" : "Nothing required is missing";
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
