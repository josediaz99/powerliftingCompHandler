document.querySelectorAll('.comp-card').forEach(function (card) {
  var el = card.querySelector('.pill');
  if (!el) return;
  var d    = new Date(el.dataset.date + 'T00:00:00');
  var now  = new Date(); now.setHours(0, 0, 0, 0);
  var diff = Math.round((d - now) / 86400000);

  if (diff <= 0) {
    el.textContent = 'Today';
    card.classList.add('is-today');
  } else if (diff === 1) {
    el.textContent = 'Tomorrow';
  } else if (diff < 7) {
    el.textContent = 'in ' + diff + ' days';
  } else {
    var w = Math.round(diff / 7);
    el.textContent = 'in ' + w + (w === 1 ? ' wk' : ' wks');
  }
});
