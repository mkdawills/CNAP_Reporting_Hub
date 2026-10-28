/* Forms (MW 2026-10-28): answers save as people go, and a slim strip shows where they are. */
(function () {
  var form = document.getElementById("runner");
  if (!form) return;

  /* ---- save as you go ---- */
  var url = form.getAttribute("data-autosave"), state = document.getElementById("savestate");
  var timer = null, inflight = false, again = false;
  function say(t) { if (state) state.textContent = t; }
  function save() {
    if (inflight) { again = true; return; }
    inflight = true; say("Saving…");
    var data = new FormData(form);
    Array.from(data.keys()).forEach(function (k) { if (k.indexOf("file-") === 0) data.delete(k); });
    data.delete("action");
    var token = form.querySelector("[name=csrfmiddlewaretoken]");
    fetch(url, { method: "POST", body: data, credentials: "same-origin",
                 headers: { "X-CSRFToken": token ? token.value : "", "X-Requested-With": "fetch" } })
      .then(function (r) { return r.json().then(function (j) { return [r.ok, j]; }); })
      .then(function (res) {
        if (res[0] && res[1].ok) say(res[1].problems && res[1].problems.length ? res[1].problems[0] : "Saved " + res[1].at);
        else say("Couldn’t save just now. Your answers are still on this page; use Save draft.");
      })
      .catch(function () { say("Couldn’t save just now. Your answers are still on this page; use Save draft."); })
      .then(function () { inflight = false; if (again) { again = false; save(); } });
  }
  function soon(e) {
    if (!url || (e.target && e.target.type === "file")) return;
    clearTimeout(timer); timer = setTimeout(save, e.type === "input" ? 1200 : 300);
  }
  if (url) { form.addEventListener("change", soon); form.addEventListener("input", soon); }

  /* ---- where am I ---- */
  var bar = document.getElementById("formprog"), txt = document.getElementById("formprog-t"), fill = document.getElementById("formprog-f");
  var minutes = parseInt(form.getAttribute("data-minutes") || "0", 10);
  function sections() { return Array.from(form.querySelectorAll("section.section")).filter(function (s) { return !s.hidden; }); }
  function update() {
    var secs = sections();
    if (!bar || secs.length < 2) { if (bar) bar.hidden = true; return; }
    var mark = window.innerHeight * 0.35, cur = 0;
    secs.forEach(function (s, i) { if (s.getBoundingClientRect().top < mark) cur = i; });
    var left = Math.max(1, Math.round(minutes * (secs.length - cur) / secs.length));
    txt.textContent = "Section " + (cur + 1) + " of " + secs.length + (minutes ? " · about " + left + " min left" : "");
    fill.style.width = Math.round(100 * (cur + 1) / secs.length) + "%";
    bar.hidden = window.scrollY < 200;
  }
  window.addEventListener("scroll", update, { passive: true });
  form.addEventListener("change", update);
  update();
})();
