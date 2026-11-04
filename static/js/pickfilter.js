/* Long checkbox lists (MW 2026-11-04): a search box and a "Show only the ones ticked" switch
   above any list of more than 12 choices, so finding one CNAP member among many takes a second.
   Ticked names always stay visible, so nothing chosen is ever hidden by a search. */
(function () {
  document.querySelectorAll(".checkgrid").forEach(function (grid) {
    var items = Array.from(grid.querySelectorAll("label")).filter(function (l) { return l.querySelector("input[type=checkbox]"); });
    if (items.length <= 12 || grid.dataset.picker) return;
    grid.dataset.picker = "1";
    var bar = document.createElement("div");
    bar.className = "pickbar";
    var box = document.createElement("input");
    box.type = "search";
    box.placeholder = "Search by name, for example: Okafor";
    box.setAttribute("aria-label", "Search this list");
    box.title = "Type part of a name to narrow the list. People you have already ticked stay visible.";
    var only = document.createElement("button");
    only.type = "button";
    only.className = "fchipbtn";
    only.title = "Shows only the choices you have ticked, so you can check them at a glance. Click again to see everyone.";
    var count = document.createElement("span");
    count.className = "small muted pickcount";
    bar.appendChild(box); bar.appendChild(only); bar.appendChild(count);
    grid.parentNode.insertBefore(bar, grid);
    var onlyOn = false;
    function apply() {
      var q = box.value.trim().toLowerCase(), shown = 0, ticked = 0;
      items.forEach(function (l) {
        var on = l.querySelector("input").checked;
        if (on) ticked++;
        var match = !q || l.textContent.toLowerCase().indexOf(q) !== -1;
        var vis = onlyOn ? on : (match || on);
        l.hidden = !vis;
        if (vis) shown++;
      });
      only.textContent = onlyOn ? "Show everyone" : "Show only the ones ticked (" + ticked + ")";
      only.classList.toggle("on", onlyOn);
      count.textContent = "Showing " + shown + " of " + items.length;
    }
    box.addEventListener("input", function () { onlyOn = false; apply(); });
    only.addEventListener("click", function () { onlyOn = !onlyOn; apply(); });
    grid.addEventListener("change", apply);
    apply();
  });
})();
