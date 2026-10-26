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
