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
  /* questions answered so far, not sections: "Section 1 of 2" meant nothing to people (MW 2026-11-03) */
  function questions() {
    return Array.from(form.querySelectorAll("section.section:not([hidden]) .q:not(.q-note)")).filter(function (q) { return !q.closest("[hidden]"); });
  }
  function answered(q) {
    if (q.querySelector("input[type=radio]:checked, input[type=checkbox]:checked, .filename")) return true;
    return Array.from(q.querySelectorAll("textarea, input[type=text], input[type=date], input[type=number], select")).some(function (el) { return (el.value || "").trim() !== ""; });
  }
  function update() {
    var qs = questions();
    if (!bar || qs.length < 2) { if (bar) bar.hidden = true; return; }
    var done = qs.filter(answered).length, left = Math.max(1, Math.round(minutes * (qs.length - done) / qs.length));
    txt.textContent = (done === qs.length ? "You’ve answered all " + qs.length + " questions." :
      "You’ve answered " + done + " of " + qs.length + " questions." + (minutes ? " About " + left + " minute" + (left === 1 ? "" : "s") + " left." : ""));
    fill.style.width = Math.round(100 * done / qs.length) + "%";
    bar.hidden = window.scrollY < 200;
  }
  window.addEventListener("scroll", update, { passive: true });
  form.addEventListener("change", update);
  form.addEventListener("input", update);
  update();
})();
