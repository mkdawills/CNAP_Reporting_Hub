// Copy buttons on suggested wording (Stevens Amendment box and similar).
document.addEventListener("click", function (e) {
  var b = e.target.closest && e.target.closest(".acktext .copy");
  if (!b) return;
  var t = b.parentNode.querySelector("span").textContent;
  try { navigator.clipboard.writeText(t); b.textContent = "Copied"; } catch (err) {}
  setTimeout(function () { b.textContent = "Copy"; }, 1500);
});
