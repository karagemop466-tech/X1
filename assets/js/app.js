/* =========================================================================
   X1 — shared site behavior. Dependency-free.
   - highlights active nav link
   - injects flagged-for-review count into the topbar
   - adds client-side sorting to data tables (click a header)
   - exposes a tiny helper for consistent source cells
   ========================================================================= */
(function () {
  "use strict";

  /* ---- Active nav highlight ---- */
  function setActiveNav() {
    var path = location.pathname.split("/").pop() || "index.html";
    var links = document.querySelectorAll(".nav a");
    links.forEach(function (a) {
      var href = a.getAttribute("href");
      if (href === path) {
        a.classList.add("active");
      }
    });
  }

  /* ---- Flagged count badge ---- */
  function injectFlaggedCount() {
    var target = document.querySelector(".nav-flag");
    if (!target) return;
    fetch("data/flagged-count.json")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && typeof d.count === "number") {
          target.textContent = "Flagged for review: " + d.count;
          target.setAttribute("title", "Open the Flagged for Review page to audit unverified items.");
        } else {
          target.textContent = "Flagged for review";
        }
      })
      .catch(function () {
        target.textContent = "Flagged for review";
      });
  }

  /* ---- Sortable tables ----
     Headers with class .sortable and data-sort="str|num" sort the column.
     Numeric sort parses numbers, falls back to string. */
  function makeSortable() {
    var tables = document.querySelectorAll("table.sortable");
    tables.forEach(function (table) {
      var ths = table.querySelectorAll("thead th.sortable");
      ths.forEach(function (th) {
        th.style.cursor = "pointer";
        th.addEventListener("click", function () {
          var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
          var mode = th.getAttribute("data-sort") === "num" ? "num" : "str";
          var asc = th.getAttribute("data-dir") !== "asc";
          ths.forEach(function (o) {
            o.setAttribute("data-dir", "");
            o.style.color = "";
          });
          th.setAttribute("data-dir", asc ? "asc" : "desc");
          th.style.color = "var(--text)";

          var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));
          rows.sort(function (a, b) {
            var av = (a.children[idx].getAttribute("data-val") || a.children[idx].textContent || "").trim();
            var bv = (b.children[idx].getAttribute("data-val") || b.children[idx].textContent || "").trim();
            var cmp;
            if (mode === "num") {
              var an = parseFloat(av.replace(/[^\d.\-]/g, ""));
              var bn = parseFloat(bv.replace(/[^\d.\-]/g, ""));
              cmp = (isNaN(an) ? -1e9 : an) - (isNaN(bn) ? -1e9 : bn);
            } else {
              cmp = av.localeCompare(bv, undefined, { numeric: true });
            }
            return asc ? cmp : -cmp;
          });
          rows.forEach(function (r) { table.tBodies[0].appendChild(r); });
        });
      });
    });
  }

  /* ---- Table row zebra + tabular nums ---- */
  function polishTables() {
    document.querySelectorAll("table.data").forEach(function (t) {
      if (!t.classList.contains("sortable")) t.classList.add("data");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    setActiveNav();
    injectFlaggedCount();
    makeSortable();
    polishTables();
  });
})();
