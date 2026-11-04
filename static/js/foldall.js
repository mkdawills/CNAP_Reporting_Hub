/* Wherever a page has two or more fold-up sections, add "Show all" and "Collapse all"
   above the first one (MW 2026-11-03: anytime there are dropdowns, there should be
   show all / collapse all). */
document.addEventListener("DOMContentLoaded", function () {
  // A captured copy of a page may already hold the injected controls (dead ones), so clear
  // them and rebuild, which also keeps a second run from doubling the bars.
  document.querySelectorAll(".foldall:not(.taskfold)").forEach(function (e) { e.remove(); });
  document.querySelectorAll(".rollcaret:not(.gcaret)").forEach(function (e) { e.remove(); });
  document.querySelectorAll(".rollhead").forEach(function (e) { e.classList.remove("rollhead"); });
  var groups = new Map();
  document.querySelectorAll("details:not(.whochip):not(.sowbox)").forEach(function (d) {
    if (d.closest("details") !== d && d.parentElement.closest("details")) return; // nested: skip
    var p = d.parentElement;
    if (!groups.has(p)) groups.set(p, []);
    groups.get(p).push(d);
  });
  groups.forEach(function (list, parent) {
    if (list.length < 2 || parent.querySelector(".foldall")) return;
    var bar = document.createElement("p");
    bar.className = "small foldall";
    var show = document.createElement("button");
    show.type = "button"; show.className = "linkbtn"; show.textContent = "Show all"; show.title = "Opens every section on this page at once, so you can read or print the whole thing.";
        var hide = document.createElement("button");
    hide.type = "button"; hide.className = "linkbtn"; hide.textContent = "Collapse all"; hide.title = "Rolls every section up to its title, so you can scan the page and open only what you need.";
    show.addEventListener("click", function () { list.forEach(function (d) { d.open = true; }); });
    hide.addEventListener("click", function () { list.forEach(function (d) { d.open = false; }); });
    bar.appendChild(show); bar.appendChild(hide);
    parent.insertBefore(bar, list[0]);
  });
});

/* Roll-up sections (MW 2026-11-03): inside a .rollup container, every <section> with an <h2>
   can be rolled up to its header, and the group gets Show all / Collapse all. Links inside the
   header still work; only the caret button toggles. */
document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".rollup").forEach(function (root) {
    var secs = Array.from(root.querySelectorAll("section, .rollsec")).filter(function (sec) {
      return sec.querySelector("h2, h3");
    });
    if (secs.length < 2) return;
    function parts(sec) {
      var head = sec.querySelector(":scope > header, :scope > .sechead, :scope > .rhead") || sec.querySelector("h2, h3");
      return Array.from(sec.children).filter(function (c) {
        return c !== head && !c.contains(head) && !(c.classList && c.classList.contains("teyebrow"));
      });
    }
    function set(sec, open) {
      parts(sec).forEach(function (el) { el.hidden = !open; });
      sec.dataset.open = open ? "1" : "0";
      var c = sec.querySelector(".rollcaret");
      if (c) c.textContent = open ? "\u25be" : "\u25b8";
      var h = sec.querySelector(".rollhead");
      if (h) h.setAttribute("aria-expanded", String(open));
    }
    secs.forEach(function (sec) {
      var h = sec.querySelector("h2, h3");
      var car = document.createElement("span");
      car.className = "rollcaret";
      car.setAttribute("aria-hidden", "true");
      h.insertBefore(car, h.firstChild);
      h.classList.add("rollhead");
      h.setAttribute("role", "button");
      h.tabIndex = 0;
      function toggle() { set(sec, sec.dataset.open !== "1"); }
      h.addEventListener("click", function (e) {
        if (e.target.closest("a, button, input, select, .whyq")) return;
        toggle();
      });
      h.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
      set(sec, true);
    });
    var bar = document.createElement("p");
    bar.className = "small foldall";
    var show = document.createElement("button");
    show.type = "button"; show.className = "linkbtn"; show.textContent = "Show all"; show.title = "Opens every section on this page at once, so you can read or print the whole thing.";
    var hide = document.createElement("button");
    hide.type = "button"; hide.className = "linkbtn"; hide.textContent = "Collapse all"; hide.title = "Rolls every section up to its title, so you can scan the page and open only what you need.";
    show.addEventListener("click", function () { secs.forEach(function (s) { set(s, true); }); });
    hide.addEventListener("click", function () { secs.forEach(function (s) { set(s, false); }); });
    bar.appendChild(show); bar.appendChild(hide);
    secs[0].parentNode.insertBefore(bar, secs[0]);
    // Pages that open rolled up, so the reader sees the big ideas first (MW 2026-11-04).
    if (root.dataset.start === "closed") secs.forEach(function (sec) { set(sec, false); });
  });
});

/* Flip a dashboard graph's axes (MW 2026-11-03). */
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest(".flipbtn");
  if (!b) return;
  var w = b.closest(".graphwrap");
  var m = w.querySelector(".gmain"), a = w.querySelector(".galt");
  m.hidden = !m.hidden;
  a.hidden = !a.hidden;
  b.textContent = m.hidden ? "Flip the axes back" : "Flip the axes";
});


/* A link to a section that is rolled up opens it first (RPPR bubbles, page anchors). */
document.addEventListener("click", function (e) {
  var a = e.target.closest && e.target.closest('a[href^="#"]');
  if (!a) return;
  var t = document.getElementById(a.getAttribute("href").slice(1));
  if (t && t.dataset.open === "0") { var h = t.querySelector(".rollhead"); if (h) h.click(); }
});
