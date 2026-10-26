// A short burst of confetti when someone finishes a survey or report. Skipped for reduced-motion users.
(function () {
  function confetti() {
    try { if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return; } catch (e) {}
    var colors = ["#512888", "#1f6857", "#7db5a4", "#e8a38c", "#f2c14e", "#4472c4"];
    var src = document.querySelector("[data-confetti], .nextup");
    var rect = src ? src.getBoundingClientRect() : { left: innerWidth / 2, top: innerHeight / 3, width: 0 };
    var ox = rect.left + rect.width / 2, oy = Math.max(40, rect.top + 20);
    var box = document.createElement("div");
    box.className = "confetti";
    box.setAttribute("aria-hidden", "true");
    for (var i = 0; i < 110; i++) {
      var s = document.createElement("i");
      var ang = Math.random() * Math.PI * 2, dist = 120 + Math.random() * 260;
      s.style.left = ox + "px";
      s.style.top = oy + "px";
      s.style.background = colors[i % colors.length];
      s.style.animationDuration = 1.6 + Math.random() * 1.2 + "s";
      s.style.setProperty("--x", Math.cos(ang) * dist + "px");
      s.style.setProperty("--y", Math.sin(ang) * dist * 0.7 - 120 + "px");
      s.style.setProperty("--r", Math.random() * 900 - 450 + "deg");
      box.appendChild(s);
    }
    document.body.appendChild(box);
    setTimeout(function () { box.remove(); }, 3200);
  }
  var el = document.querySelector("[data-confetti]");
  if (!el) return;
  var key = "cnap-confetti-" + el.getAttribute("data-confetti");
  try { if (sessionStorage.getItem(key)) return; sessionStorage.setItem(key, "1"); } catch (e) {}
  confetti();
})();
