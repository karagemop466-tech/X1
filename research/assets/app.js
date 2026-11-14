/* Small progressive enhancements for the X1 dashboard:
   - client-side filtering of any table with [data-filter]
   - sortable columns for tables with [data-sort]
   No external dependencies, no network calls. */
(function () {
  "use strict";

  function cellValue(row, index) {
    var cell = row.children[index];
    if (!cell) return "";
    var raw = cell.getAttribute("data-sort-value");
    if (raw !== null) {
      var num = parseFloat(raw);
      return isNaN(num) ? raw.toLowerCase() : num;
    }
    return cell.textContent.trim().toLowerCase();
  }

  document.querySelectorAll("table[data-sort]").forEach(function (table) {
    var headers = table.querySelectorAll("thead th");
    headers.forEach(function (th, index) {
      th.style.cursor = "pointer";
      th.title = "Sort by this column";
      th.addEventListener("click", function () {
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        var asc = th.getAttribute("data-dir") !== "asc";
        rows.sort(function (a, b) {
          var va = cellValue(a, index), vb = cellValue(b, index);
          if (va < vb) return asc ? -1 : 1;
          if (va > vb) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { body.appendChild(r); });
        th.setAttribute("data-dir", asc ? "asc" : "desc");
      });
    });
  });

  document.querySelectorAll("[data-filter]").forEach(function (input) {
    var selector = input.getAttribute("data-filter");
    var targets = document.querySelectorAll(selector);
    input.addEventListener("input", function () {
      var q = input.value.toLowerCase().trim();
      targets.forEach(function (row) {
        row.style.display = !q || row.textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
      });
    });
  });

  document.querySelectorAll("[data-filter-select]").forEach(function (input) {
    var selector = input.getAttribute("data-filter-select");
    var column = parseInt(input.getAttribute("data-filter-column") || "0", 10);
    var targets = document.querySelectorAll(selector);
    input.addEventListener("input", function () {
      var q = input.value.toLowerCase().trim();
      targets.forEach(function (row) {
        var cell = row.children[column];
        var v = cell ? cell.textContent.trim().toLowerCase() : "";
        row.style.display = !q || v.indexOf(q) !== -1 ? "" : "none";
      });
    });
  });
})();
