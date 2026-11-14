// X1 console - filter + sort only. No network calls, no frameworks.
(function () {
  function ready(fn){ document.readyState!=='loading'?fn():document.addEventListener('DOMContentLoaded',fn); }
  ready(function () {
    document.querySelectorAll('[data-filter-for]').forEach(function (input) {
      var target = document.getElementById(input.getAttribute('data-filter-for'));
      if (!target) return;
      var col = input.getAttribute('data-filter-col');
      input.addEventListener('input', function () {
        var q = input.value.toLowerCase().trim();
        var rows = target.querySelectorAll('tbody tr');
        var shown = 0;
        rows.forEach(function (tr) {
          var hay = col ? (tr.children[col] ? tr.children[col].textContent : '') : tr.textContent;
          var ok = hay.toLowerCase().indexOf(q) !== -1;
          tr.style.display = ok ? '' : 'none';
          if (ok) shown++;
        });
        var c = document.getElementById(input.getAttribute('data-filter-for') + '-count');
        if (c) c.textContent = shown + ' of ' + rows.length + ' rows shown';
      });
    });
    document.querySelectorAll('table.sortable').forEach(function (table) {
      var ths = table.querySelectorAll('thead th');
      ths.forEach(function (th, idx) {
        th.addEventListener('click', function () {
          var body = table.tBodies[0];
          var rows = Array.prototype.slice.call(body.rows);
          var dir = th.dataset.dir === 'asc' ? 'desc' : 'asc';
          ths.forEach(function (o) { o.dataset.dir = ''; });
          th.dataset.dir = dir;
          var numeric = th.classList.contains('num');
          rows.sort(function (a, b) {
            var x = a.cells[idx].textContent.trim(), y = b.cells[idx].textContent.trim();
            if (numeric) {
              var nx = parseFloat(x.replace(/[,%]/g, '')), ny = parseFloat(y.replace(/[,%]/g, ''));
              if (isNaN(nx)) nx = -Infinity; if (isNaN(ny)) ny = -Infinity;
              return dir === 'asc' ? nx - ny : ny - nx;
            }
            return dir === 'asc' ? x.localeCompare(y) : y.localeCompare(x);
          });
          rows.forEach(function (r) { body.appendChild(r); });
        });
      });
    });
  });
})();
