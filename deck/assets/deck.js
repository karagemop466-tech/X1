function filt(inp, tblId){
  var q = inp.value.toLowerCase();
  var rows = document.getElementById(tblId).querySelectorAll('tbody tr');
  rows.forEach(function(r){
    r.style.display = r.innerText.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
  });
}
