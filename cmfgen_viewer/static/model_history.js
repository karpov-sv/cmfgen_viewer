(function () {
  const all = document.querySelector('[data-history-select-all]');
  if (all) {
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
  }

  const archiveList = document.querySelector('[data-history-archives]');
  const age = document.getElementById('history-age');
  if (archiveList) {
    const key = 'cmfgen-history-scroll:' + location.pathname + ':' + (age ? age.value : '0');
    try { archiveList.scrollTop = Number(sessionStorage.getItem(key)) || 0; } catch (_) { /* Storage may be disabled. */ }
    archiveList.addEventListener('scroll', function () {
      try { sessionStorage.setItem(key, String(archiveList.scrollTop)); } catch (_) { /* Optional convenience. */ }
    });
  }

  const fileFilter = document.querySelector('[data-history-file-filter]');
  if (fileFilter) {
    const rows = Array.from(document.querySelectorAll('[data-history-file-row]'));
    const empty = document.querySelector('[data-history-file-empty]');
    fileFilter.addEventListener('input', function () {
      const query = fileFilter.value.trim().toLowerCase();
      rows.forEach(row => { row.hidden = !row.textContent.toLowerCase().includes(query); });
      if (empty) empty.hidden = rows.length === 0 || rows.some(row => !row.hidden);
    });
  }
  const diff = document.querySelector('[data-history-diff]');
  if (diff) {
    const wrap = document.querySelector('[data-history-wrap]');
    const changes = document.querySelector('[data-history-changes]');
    wrap.addEventListener('change', () => diff.classList.toggle('history-diff-wrap', wrap.checked));
    changes.addEventListener('change', () => diff.classList.toggle('history-diff-changes', changes.checked));
  }
})();
