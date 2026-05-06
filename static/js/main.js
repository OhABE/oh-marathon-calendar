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

function clearAllEvents() {
  if (!confirm('全大会データを削除します。よろしいですか？')) return;
  fetch('/admin/events/clear-all', { method: 'POST' })
    .then(r => r.json())
    .then(data => { showToast(data.message); setTimeout(() => location.reload(), 1500); })
    .catch(() => showToast('削除に失敗しました'));
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

// 直近の大会を最初から表示（リスト表示時のみ）
window.addEventListener('DOMContentLoaded', () => {
  const next = document.getElementById('next-event');
  if (next) next.scrollIntoView({ behavior: 'instant', block: 'start' });
});

// ── カレンダービュー ───────────────────────────────
let calYear, calMonth;

function toggleView(view) {
  const listView = document.getElementById('listView');
  const calView  = document.getElementById('calendarView');
  const btnList  = document.getElementById('btnListView');
  const btnCal   = document.getElementById('btnCalView');
  if (view === 'cal') {
    listView.style.display = 'none';
    calView.style.display  = 'block';
    btnList.classList.remove('active');
    btnCal.classList.add('active');
    if (calYear === undefined) initCalendar();
    else renderCalendar();
  } else {
    listView.style.display = 'block';
    calView.style.display  = 'none';
    btnList.classList.add('active');
    btnCal.classList.remove('active');
  }
}

function initCalendar() {
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const upcoming = (typeof EVENTS_JSON !== 'undefined') &&
    EVENTS_JSON.find(e => e.date && e.date >= todayStr);
  if (upcoming) {
    const d = new Date(upcoming.date + 'T00:00:00');
    calYear  = d.getFullYear();
    calMonth = d.getMonth();
  } else {
    calYear  = today.getFullYear();
    calMonth = today.getMonth();
  }
  renderCalendar();
}

function changeMonth(delta) {
  calMonth += delta;
  if (calMonth > 11) { calMonth = 0; calYear++; }
  if (calMonth < 0)  { calMonth = 11; calYear--; }
  renderCalendar();
}

function renderCalendar() {
  document.getElementById('calMonthTitle').textContent =
    `${calYear}年${calMonth + 1}月`;

  const todayStr   = new Date().toISOString().slice(0, 10);
  const monthStr   = String(calMonth + 1).padStart(2, '0');
  const firstDay   = new Date(calYear, calMonth, 1);
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const startDow   = firstDay.getDay();
  const prevLast   = new Date(calYear, calMonth, 0).getDate();

  // 日付ごとにイベントをまとめる
  const evByDate = {};
  if (typeof EVENTS_JSON !== 'undefined') {
    EVENTS_JSON.forEach(ev => {
      if (!ev.date) return;
      if (!evByDate[ev.date]) evByDate[ev.date] = [];
      evByDate[ev.date].push(ev);
    });
  }

  const distClass = { 'フル':'dist-full','ハーフ':'dist-half','ウルトラ':'dist-ultra','トレイル':'dist-trail','リレー':'dist-relay' };

  let html = '';

  // 前月の余白
  for (let i = 0; i < startDow; i++) {
    html += `<div class="cal-day other-month"><span class="cal-date">${prevLast - startDow + i + 1}</span></div>`;
  }

  // 当月の日付
  for (let d = 1; d <= daysInMonth; d++) {
    const dateStr = `${calYear}-${monthStr}-${String(d).padStart(2, '0')}`;
    const isToday = dateStr === todayStr;
    const dow = (startDow + d - 1) % 7;
    const cls = ['cal-day', isToday ? 'today' : '', dow === 0 ? 'sun' : dow === 6 ? 'sat' : ''].filter(Boolean).join(' ');
    html += `<div class="${cls}"><span class="cal-date">${d}</span>`;
    (evByDate[dateStr] || []).forEach(ev => {
      const dc = distClass[ev.distance] || 'dist-other';
      const name = ev.name.length > 13 ? ev.name.slice(0, 13) + '…' : ev.name;
      html += `<a href="${ev.url || '#'}" target="_blank" class="cal-event ${dc}" title="${ev.name}">${name}</a>`;
    });
    html += '</div>';
  }

  // 次月の余白
  const total = startDow + daysInMonth;
  const remain = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let d = 1; d <= remain; d++) {
    html += `<div class="cal-day other-month"><span class="cal-date">${d}</span></div>`;
  }

  document.getElementById('calDays').innerHTML = html;
}
