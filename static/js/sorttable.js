// Every table with a header row sorts by that column on click; click again to flip (MW 2026-11-03).
// One listener for the whole page, so tables drawn later (such as a flipped table) sort too.
(function () {
  function mark(root) {
    (root || document).querySelectorAll("table thead th").forEach(function (th) {
      if (th.textContent.trim()) th.classList.add("sorth");
    });
  }
  mark();
  window.cnapMarkSortable = mark;
  document.addEventListener("click", function (e) {
    var th = e.target.closest && e.target.closest("th.sorth");
    if (!th || e.target.closest("a, button, input, select")) return;
    var table = th.closest("table"), body = table.tBodies[0];
    if (!body) return;
    var col = Array.from(th.parentNode.children).indexOf(th);
    var dir = th.classList.contains("asc") ? -1 : 1;
    table.querySelectorAll("th.sorth").forEach(function (h) { h.classList.remove("asc", "desc"); });
    th.classList.add(dir === 1 ? "asc" : "desc");
    function key(r) {
      var t = (r.cells[col] ? r.cells[col].textContent : "").trim().toLowerCase();
      var n = t.replace(/[$,%\s]/g, "");
      return /^-?\d+(\.\d+)?$/.test(n) ? parseFloat(n) : t;
    }
    var rows = Array.from(body.rows);
    var total = rows.filter(function (r) { return /^total/i.test((r.cells[0] || {}).textContent || ""); });
    rows.filter(function (r) { return total.indexOf(r) === -1; })
      .sort(function (a, b) {
        var x = key(a), y = key(b);
        if (typeof x === "number" && typeof y === "number") return dir * (x - y);
        return dir * String(x).localeCompare(String(y), undefined, { numeric: true });
      })
      .concat(total)
      .forEach(function (r) { body.appendChild(r); });
  });
})();


// Drag a header to move its column; a Reset columns link puts everything back (MW 2026-11-03).
(function () {
  document.querySelectorAll("table").forEach(function (table) {
    var head = table.tHead, body = table.tBodies[0];
    if (!head || !body || table.querySelector("colgroup") || !head.rows.length || head.rows.length > 1) return;
    var ths = Array.from(head.rows[0].cells);
    if (ths.length < 3) return;
    var original = null, resetLink = null, from = null;
    function allRows() { return [head.rows[0]].concat(Array.from(body.rows)); }
    function fullRow(r) { return r.cells.length === ths.length; }
    function snapshot() {
      if (original) return;
      original = allRows().map(function (r) { return Array.from(r.cells); });
    }
    function showReset() {
      if (resetLink) return;
      resetLink = document.createElement("button");
      resetLink.type = "button";
      resetLink.className = "btn small ghost colreset";
      resetLink.textContent = "Reset the columns";
      resetLink.addEventListener("click", function () {
        original.forEach(function (cells, i) {
          var r = allRows()[i];
          if (!r) return;
          cells.forEach(function (c) { r.appendChild(c); });
        });
        resetLink.remove();
        resetLink = null;
      });
      table.parentNode.insertBefore(resetLink, table);
    }
    ths.forEach(function (th, idx) {
      th.draggable = true;
      th.addEventListener("dragstart", function (e) { from = Array.from(head.rows[0].cells).indexOf(th); snapshot(); try { e.dataTransfer.setData("text/plain", ""); } catch (err) {} });
      th.addEventListener("dragover", function (e) { e.preventDefault(); });
      th.addEventListener("drop", function (e) {
        e.preventDefault();
        var to = Array.from(head.rows[0].cells).indexOf(th);
        if (from === null || to === from) return;
        allRows().forEach(function (r) {
          if (!fullRow(r)) return;
          var moving = r.cells[from], target = r.cells[to];
          if (!moving || !target) return;
          if (to > from) target.insertAdjacentElement("afterend", moving);
          else target.insertAdjacentElement("beforebegin", moving);
        });
        from = null;
        showReset();
      });
    });
  });
})();


// Flip rows and columns on summary tables (MW 2026-11-04): the same numbers, the other way around.
// Only for count tables with one header row and no merged cells; record lists stay as they are.
(function () {
  document.querySelectorAll("table.cnttab, table.dashtab").forEach(function (table) {
    var head = table.tHead, body = table.tBodies[0];
    if (!head || !body || head.rows.length !== 1) return;
    if (table.querySelector("[colspan], [rowspan]")) return;
    var cols = head.rows[0].cells.length, rows = Array.from(body.rows);
    if (cols < 3 || rows.length < 2) return;
    if (rows.some(function (r) { return r.cells.length !== cols; })) return;

    var flipped = document.createElement("table");
    flipped.className = table.className + " flipped";
    flipped.title = (table.title ? table.title + " " : "") + "Rows and columns are flipped.";
    var fh = flipped.createTHead().insertRow();
    var grid = [head.rows[0]].concat(rows).map(function (r) { return Array.from(r.cells); });
    grid.forEach(function (row, i) {
      var th = document.createElement("th");
      th.innerHTML = row[0].innerHTML;
      if (i > 0) {
        th.className = "num";
        th.title = "The \u201c" + row[0].textContent.trim() + "\u201d row of the original table, turned into a column. Click \u201cFlip back\u201d to see it as a row again.";
      } else {
        th.title = "Each row here was a column in the original table.";
      }
      fh.appendChild(th);
    });
    var fb = flipped.createTBody();
    for (var j = 1; j < cols; j++) {
      var tr = fb.insertRow();
      grid.forEach(function (row, i) {
        var cell = document.createElement("td");
        cell.innerHTML = i === 0 ? "<strong>" + row[j].innerHTML + "</strong>" : row[j].innerHTML;
        if (i > 0) { cell.className = (row[j].className || "") + " num"; cell.style.cssText = row[j].style.cssText; }
        tr.appendChild(cell);
      });
    }
    flipped.hidden = true;
    var wrap = table.parentNode.classList && table.parentNode.classList.contains("scroll") ? table.parentNode : table;
    wrap.parentNode.insertBefore(flipped, wrap.nextSibling);
    if (window.cnapMarkSortable) window.cnapMarkSortable(flipped.parentNode);

    var bar = document.createElement("p");
    bar.className = "flipbar";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "fchipbtn";
    btn.textContent = "Flip the table’s rows and columns";
    btn.title = "Turns the table just below this button the other way: the row labels become column headers and the column headers become rows. Click again to turn it back.";
    btn.addEventListener("click", function () {
      var on = flipped.hidden;
      flipped.hidden = !on;
      wrap.hidden = on;
      btn.textContent = on ? "Flip the table back" : "Flip the table’s rows and columns";
      btn.classList.toggle("on", on);
    });
    bar.appendChild(btn);
    wrap.parentNode.insertBefore(bar, wrap);
  });
})();
