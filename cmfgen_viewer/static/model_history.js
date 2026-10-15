(function () {
  const all = document.querySelector('[data-history-select-all]');
  if (!all) return;
  const boxes = Array.from(document.querySelectorAll('input[name="archive_id"]:not(:disabled)'));
  const count = document.querySelector('[data-history-selection]');
  function update() {
    const selected = boxes.filter(box => box.checked).length;
    all.checked = boxes.length > 0 && selected === boxes.length;
    all.indeterminate = selected > 0 && selected < boxes.length;
    if (count) count.textContent = selected + ' selected';
  }
  all.addEventListener('change', function () {
    boxes.forEach(box => { box.checked = all.checked; });
    update();
  });
  boxes.forEach(box => box.addEventListener('change', update));
  update();
})();
