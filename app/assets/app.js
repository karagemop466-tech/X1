/* X1 dashboard: table filter, column sort, and nothing else.
   No network calls, no frameworks. Safe to open from file:// or GitHub Pages. */
(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  function text(cell) {
    return (cell.getAttribute("data-sort") || cell.textContent || "").trim();
  }

  ready(function () {
    document.querySelectorAll("[data-filter-for]").forEach(function (box) {
      var id = box.getAttribute("data-filter-for");
      var table = document.getElementById(id);
      if (!table) return;
      var body = table.tBodies[0];
      if (!body) return;
      var colSel = document.querySelector('[data-col-for="' + id + '"]');
      var counter = document.querySelector('[data-count-for="' + id + '"]');
      var rows = Array.prototype.slice.call(body.rows);
      var colIdx = -1;

      function apply() {
        var q = box.value.toLowerCase().trim();
        var sel = colSel ? colSel.value : "";
        colIdx = colSel && colSel.value !== "" ? parseInt(sel, 10) : -1;
        var shown = 0;
        rows.forEach(function (tr) {
          var ok = true;
          if (q) ok = tr.textContent.toLowerCase().indexOf(q) >= 0;
          if (ok && colIdx >= 0) {
            var cell = tr.cells[colIdx];
            if (!cell || !cell.textContent.trim()) ok = false;
          }
          tr.style.display = ok ? "" : "none";
          if (ok) shown++;
        });
        if (counter) counter.textContent = shown + " of " + rows.length + " rows shown";
      }

      box.addEventListener("input", apply);
      if (colSel) colSel.addEventListener("change", apply);
      if (counter) counter.textContent = rows.length + " of " + rows.length + " rows shown";
    });

    document.querySelectorAll("table[data-sortable] thead th").forEach(function (th) {
      th.style.cursor = "pointer";
      th.title = "Sort by this column";
      var dir = 1;
      th.addEventListener("click", function () {
        var table = th.closest("table");
        var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = text(a.cells[idx] || a.cells[0]);
          var y = text(b.cells[idx] || b.cells[0]);
          var nx = parseFloat(x.replace(/[^0-9eE.+-]/g, ""));
          var ny = parseFloat(y.replace(/[^0-9eE.+-]/g, ""));
          var c;
          if (!isNaN(nx) && !isNaN(ny) && x !== "" && y !== "") c = nx - ny;
          else c = x.localeCompare(y);
          return c * dir;
        });
        rows.forEach(function (r) { body.appendChild(r); });
        dir = -dir;
        th.setAttribute("data-dir", dir > 0 ? "asc" : "desc");
      });
    });
  });
})();
