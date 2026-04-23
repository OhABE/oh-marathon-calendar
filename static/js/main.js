function openAddModal() {
  document.getElementById('addModal').style.display = 'block';
  document.getElementById('overlay').style.display = 'block';
}
function closeAddModal() {
  document.getElementById('addModal').style.display = 'none';
  document.getElementById('overlay').style.display = 'none';
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

function togglePhotoForm(eventId) {
  const form = document.getElementById('photo-form-' + eventId);
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function openPhoto(src) {
  const lb = document.getElementById('lightbox');
  document.getElementById('lightbox-img').src = src;
  lb.style.display = 'flex';
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
