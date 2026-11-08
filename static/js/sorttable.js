// Every table with a header row sorts by that column on click; click again to flip (MW 2026-11-03).
// One listener for the whole page, so tables drawn later (such as a flipped table) sort too.
(function () {
  function mark(root) {
    (root || document).querySelectorAll("table:not(.nosort) thead th").forEach(function (th) {
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


// Drag a header to move its column (MW 2026-11-03), on every table (MW 2026-11-07), on computers only.
// The order is remembered in this browser for this page; "Reset the columns" puts the standard order back.
// Downloads always keep the standard order. Tables with grouped (two-row) headers keep their order.
(function () {
  if (!window.matchMedia || !window.matchMedia("(pointer: fine)").matches) return;
  function store(k, v) { try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function load(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch (e) { return null; } }
  document.querySelectorAll("table").forEach(function (table, tIndex) {
    var head = table.tHead, body = table.tBodies[0];
    if (!head || !body || head.rows.length !== 1) return;
    var n = head.rows[0].cells.length;
    if (n < 2 || table.closest(".flipped") || table.classList.contains("flipped")) return;
    if (head.querySelector("[colspan]")) return;
    var key = "cols:" + location.pathname + ":" + tIndex + ":" + Array.from(head.rows[0].cells).map(function (c) { return c.textContent.trim(); }).join("|");
    var cols = table.querySelector("colgroup") ? Array.from(table.querySelectorAll("colgroup > col")) : null;
    Array.from(head.rows[0].cells).forEach(function (c, i) { c.dataset.colOrig = i; });
    function rows() { return [head.rows[0]].concat(Array.from(body.rows)).concat(table.tFoot ? Array.from(table.tFoot.rows) : []); }
    function order() { return Array.from(head.rows[0].cells).map(function (c) { return +c.dataset.colOrig; }); }
    function apply(ord) {
      // ord lists original indexes in the new order
      var cur = order();
      rows().forEach(function (r) {
        if (r.cells.length !== n) return;
        var byOrig = {};
        Array.from(r.cells).forEach(function (c, i) { byOrig[cur[i]] = c; });
        ord.forEach(function (o) { if (byOrig[o]) r.appendChild(byOrig[o]); });
      });
      if (cols && cols.length === n) {
        var cg = cols[0].parentNode, byO = {};
        cols.forEach(function (c, i) { byO[cur[i]] = c; });
        ord.forEach(function (o) { if (byO[o]) cg.appendChild(byO[o]); });
        cols = Array.from(cg.children);
      }
    }
    var note = null;
    function showNote() {
      if (note) return;
      note = document.createElement("p");
      note.className = "colnote";
      note.innerHTML = "<span>Columns reordered on this computer.</span> ";
      var b = document.createElement("button");
      b.type = "button"; b.className = "linkbtn colreset"; b.textContent = "Reset the columns";
      b.addEventListener("click", function () {
        apply(order().slice().sort(function (a, c) { return a - c; }));
        store(key, null); note.remove(); note = null;
      });
      note.appendChild(b);
      var wrap = table.parentNode.classList && table.parentNode.classList.contains("scroll") ? table.parentNode : table;
      wrap.parentNode.insertBefore(note, wrap);
    }
    var saved = load(key);
    if (saved && saved.length === n && saved.join() !== order().join()) { apply(saved); showNote(); }
    var from = null;
    Array.from(head.rows[0].cells).forEach(function (th) {
      th.draggable = true;
      th.classList.add("coldrag");
      th.title = (th.title ? th.title + " " : "") + "Drag to move this column.";
      th.addEventListener("dragstart", function (e) { from = Array.from(head.rows[0].cells).indexOf(th); th.classList.add("dragging"); try { e.dataTransfer.setData("text/plain", ""); e.dataTransfer.effectAllowed = "move"; } catch (err) {} });
      th.addEventListener("dragend", function () { th.classList.remove("dragging"); head.querySelectorAll(".dropto").forEach(function (x) { x.classList.remove("dropto"); }); });
      th.addEventListener("dragover", function (e) { e.preventDefault(); th.classList.add("dropto"); });
      th.addEventListener("dragleave", function () { th.classList.remove("dropto"); });
      th.addEventListener("drop", function (e) {
        e.preventDefault(); th.classList.remove("dropto");
        var to = Array.from(head.rows[0].cells).indexOf(th);
        if (from === null || to === from) return;
        var ord = order(), moved = ord.splice(from, 1)[0];
        ord.splice(to, 0, moved);
        apply(ord); from = null;
        var standard = ord.slice().sort(function (a, c) { return a - c; }).join();
        if (ord.join() === standard) { store(key, null); if (note) { note.remove(); note = null; } }
        else { store(key, ord); showNote(); }
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

// The sort arrow stays on the same line as the header's last word (MW 2026-11-08): the last word and the arrow
// are joined in one unbreakable piece, so a narrow column wraps the words, never the arrow alone.
(function () {
  function glue(th) {
    if (th.querySelector(".sortglue")) return;
    var walker = document.createTreeWalker(th, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { return n.nodeValue.trim() && !n.parentNode.closest(".whyq, .whyb, .sr") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; }
    });
    var last = null, n;
    while ((n = walker.nextNode())) last = n;
    var g = document.createElement("span");
    g.className = "sortglue";
    if (last) {
      var text = last.nodeValue.replace(/\s+$/, "");
      var cut = text.lastIndexOf(" ") + 1;
      last.nodeValue = text.slice(0, cut);
      g.appendChild(document.createTextNode(text.slice(cut)));
      last.parentNode.insertBefore(g, last.nextSibling);
    } else th.appendChild(g);
    var a = document.createElement("span");
    a.className = "sortarr";
    a.setAttribute("aria-hidden", "true");
    g.appendChild(a);
  }
  function run() { document.querySelectorAll("body.proto th.sorth").forEach(glue); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function () { setTimeout(run, 0); });
  else setTimeout(run, 0);
})();
