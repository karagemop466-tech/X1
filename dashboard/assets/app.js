// Minimal, dependency-free table helpers: live text filter and click-to-sort.
(function () {
  function parse(v) {
    var n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
    return isNaN(n) ? null : n;
  }
  document.querySelectorAll('table.sortable').forEach(function (t) {
    var ths = t.querySelectorAll('th');
    ths.forEach(function (th, idx) {
      th.addEventListener('click', function () {
        var tbody = t.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        var asc = th.dataset.asc !== '1';
        ths.forEach(function (h) { delete h.dataset.asc; });
        th.dataset.asc = asc ? '1' : '0';
        rows.sort(function (a, b) {
          var x = a.cells[idx].innerText.trim(), y = b.cells[idx].innerText.trim();
          var nx = parse(x), ny = parse(y);
          var r = (nx !== null && ny !== null) ? nx - ny : x.localeCompare(y);
          return asc ? r : -r;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });
  document.querySelectorAll('input.filter').forEach(function (inp) {
    var t = document.getElementById(inp.dataset.target);
    inp.addEventListener('input', function () {
      var q = inp.value.toLowerCase();
      Array.prototype.forEach.call(t.tBodies[0].rows, function (r) {
        r.style.display = r.innerText.toLowerCase().indexOf(q) > -1 ? '' : 'none';
      });
    });
  });
})();
