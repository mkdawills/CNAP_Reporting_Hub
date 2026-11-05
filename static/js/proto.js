/* Screen 21 prototype: the section navigator (MW 2026-11-05).
   Read-only helper: it never changes answers or submits anything.
   - Highlights the section you are reading.
   - Shows, per section, whether its questions have answers: all, some, or none yet.
     This is a description of what is filled in, not a promise that the section is valid;
     the server still checks every required answer when you press Submit. */
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
  function state(sec) {
    var qs = questionsIn(sec).map(answered).filter(function (v) { return v !== null; });
    if (!qs.length) return "";
    var n = qs.filter(Boolean).length;
    return n === 0 ? "none" : n === qs.length ? "all" : "some";
  }
  var words = { all: "All questions answered", some: "Some questions answered", none: "Not answered yet" };
  function refresh() {
    links.forEach(function (a) {
      var sec = document.getElementById("sec-" + a.dataset.nav);
      if (!sec) return;
      var s = state(sec);
      a.dataset.state = s;
      var sr = a.querySelector(".p21-navstate");
      if (sr) sr.textContent = s ? " (" + words[s] + ")" : "";
      a.title = s ? words[s] : "";
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
