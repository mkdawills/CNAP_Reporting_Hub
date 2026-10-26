// A short burst of confetti when someone finishes a survey or report. Skipped for reduced-motion users.
(function () {
  function confetti() {
    try { if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return; } catch (e) {}
    var colors = ["#512888", "#1f6857", "#7db5a4", "#e8a38c", "#f2c14e", "#4472c4"];
    var box = document.createElement("div");
    box.className = "confetti";
    box.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 90; i++) {
      var s = document.createElement("i");
      s.style.left = Math.random() * 100 + "vw";
      s.style.background = colors[i % colors.length];
      s.style.animationDelay = Math.random() * 0.4 + "s";
      s.style.animationDuration = 2 + Math.random() * 1.4 + "s";
      s.style.setProperty("--x", Math.random() * 160 - 80 + "px");
      s.style.setProperty("--r", Math.random() * 720 - 360 + "deg");
      box.appendChild(s);
    }
    document.body.appendChild(box);
    setTimeout(function () { box.remove(); }, 4200);
  }
  var el = document.querySelector("[data-confetti]");
  if (!el) return;
  var key = "cnap-confetti-" + el.getAttribute("data-confetti");
  try { if (sessionStorage.getItem(key)) return; sessionStorage.setItem(key, "1"); } catch (e) {}
  confetti();
})();
