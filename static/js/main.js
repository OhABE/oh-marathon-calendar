function openAddModal() {
  document.getElementById('addModal').style.display = 'block';
  document.getElementById('overlay').style.display = 'block';
}
function closeAddModal() {
  document.getElementById('addModal').style.display = 'none';
  document.getElementById('overlay').style.display = 'none';
}
function openPinModal() {
  document.getElementById('pinModal').style.display = 'block';
  document.getElementById('pinOverlay').style.display = 'block';
}
function closePinModal() {
  document.getElementById('pinModal').style.display = 'none';
  document.getElementById('pinOverlay').style.display = 'none';
}
function openCalModal() {
  document.getElementById('calModal').style.display = 'block';
  document.getElementById('calOverlay').style.display = 'block';
}
function closeCalModal() {
  document.getElementById('calModal').style.display = 'none';
  document.getElementById('calOverlay').style.display = 'none';
}
function copyUrl(id) {
  const text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(() => showToast('URLをコピーしました！'));
}


function openEditModal(ev) {
  document.getElementById('edit_name').value = ev.name || '';
  document.getElementById('edit_date').value = ev.date || '';
  document.getElementById('edit_prefecture').value = ev.prefecture || '';
  document.getElementById('edit_region').value = ev.region || '';
  document.getElementById('edit_distance').value = ev.distance || '';
  document.getElementById('edit_venue').value = ev.venue || '';
  document.getElementById('edit_entry_start').value = ev.entry_start || '';
  document.getElementById('edit_entry_end').value = ev.entry_end || '';
  document.getElementById('edit_fee').value = ev.fee || '';
  document.getElementById('edit_time_limit').value = ev.time_limit || '';
  document.getElementById('edit_url').value = ev.url || '';
  document.getElementById('edit_entry_url').value = ev.entry_url || '';
  document.getElementById('edit_entry_site').value = ev.entry_site || '';
  document.getElementById('edit_confirmed').checked = ev.confirmed == 1;
  document.getElementById('editForm').action = '/admin/events/' + ev.id + '/edit';
  document.getElementById('editModal').style.display = 'block';
  document.getElementById('editOverlay').style.display = 'block';
}
function closeEditModal() {
  document.getElementById('editModal').style.display = 'none';
  document.getElementById('editOverlay').style.display = 'none';
}

function runScrape() {
  const btn = document.querySelector('.btn-scrape');
  btn.textContent = '取得中...';
  btn.disabled = true;
  fetch('/scrape', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      showToast(data.message);
      setTimeout(() => location.reload(), 2000);
    })
    .catch(() => showToast('取得に失敗しました'))
    .finally(() => { btn.textContent = '🔄 自動取得'; btn.disabled = false; });
}

function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.style.display = 'block';
  setTimeout(() => { toast.style.display = 'none'; }, 3000);
}
