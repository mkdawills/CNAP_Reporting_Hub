// n / % column switch for report tables. Remembers the choice per browser.
(function () {
  function apply(mode) {
    document.body.classList.toggle("only-n", mode === "n");
    document.body.classList.toggle("only-p", mode === "p");
    document.querySelectorAll(".reptab .grp").forEach(function (c) { c.colSpan = mode === "both" ? 2 : 1; });
    document.querySelectorAll(".nview button").forEach(function (b) { b.classList.toggle("on", b.dataset.nview === mode); });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".nview button");
    if (!b) return;
    apply(b.dataset.nview);
    try { localStorage.setItem("cnap-nview", b.dataset.nview); } catch (err) {}
  });
  var saved = "both";
  try { saved = localStorage.getItem("cnap-nview") || "both"; } catch (err) {}
  if (document.querySelector(".nview")) apply(saved);
})();
// Means / Means and SD switch for the year-over-year table.
(function () {
  function apply(mode) {
    document.body.classList.toggle("show-sd", mode === "sd");
    document.querySelectorAll(".lontab .sdgrp").forEach(function (c) {
      var n = parseInt(c.getAttribute("data-span") || "1", 10);
      c.colSpan = mode === "sd" ? n * 2 : n;
    });
    document.querySelectorAll(".sdview button").forEach(function (b) { b.classList.toggle("on", b.dataset.sdview === mode); });
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest(".sdview button");
    if (!b) return;
    apply(b.dataset.sdview);
    try { localStorage.setItem("cnap-sdview", b.dataset.sdview); } catch (err) {}
  });
  var saved = "sd";
  try { saved = localStorage.getItem("cnap-sdview") || "sd"; } catch (err) {}
  if (document.querySelector(".sdview")) apply(saved);
})();
// "Show all / Collapse all" for the item-by-item tables on results pages (MW, 2026-10-26).
(function () {
  function label(btn) {
    var all = document.querySelectorAll("details.tmore");
    var anyClosed = Array.prototype.some.call(all, function (d) { return !d.open; });
    btn.textContent = anyClosed ? "Show all tables" : "Collapse all tables";
    btn.setAttribute("aria-expanded", anyClosed ? "false" : "true");
  }
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-expand-all]");
    if (!btn) return;
    var all = document.querySelectorAll("details.tmore");
    var open = Array.prototype.some.call(all, function (d) { return !d.open; });
    all.forEach(function (d) { d.open = open; });
    document.querySelectorAll("[data-expand-all]").forEach(label);
  });
  document.addEventListener("toggle", function (e) {
    if (e.target.matches && e.target.matches("details.tmore")) document.querySelectorAll("[data-expand-all]").forEach(label);
  }, true);
  document.querySelectorAll("[data-expand-all]").forEach(function (b) {
    if (!document.querySelector("details.tmore")) { b.hidden = true; return; }
    label(b);
  });
})();
