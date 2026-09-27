'use strict';

/* ───────── 저장 (이 휴대폰의 localStorage에만 저장) ───────── */
const KEY = 'hapjang.v1';
const DEFAULTS = {
  settings: { sound: true, click: true, haptic: true },
  wish: '',
  tab: 'beads',
  beads: { mode: 108, 21: { count: 0, rounds: 0 }, 108: { count: 0, rounds: 0 }, days: {} },
  bowl: { interval: 5, wake: false },
  favs: [null, null, null],
  visits: [],
};

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY));
    if (saved && typeof saved === 'object') return merge(DEFAULTS, saved);
  } catch (e) { /* 저장소를 못 쓰면 기본값으로 */ }
  return structuredClone(DEFAULTS);
}
function merge(base, extra) {
  const out = structuredClone(base);
  for (const k of Object.keys(extra || {})) {
    const b = base[k], v = extra[k];
    out[k] = b && v && typeof b === 'object' && !Array.isArray(b) && typeof v === 'object' ? merge(b, v) : v;
  }
  return out;
}
let S = load();
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* 저장 실패는 무시 */ }
}

const $ = (sel) => document.querySelector(sel);
function today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/* ───────── 소리 ───────── */
try { if (navigator.audioSession) navigator.audioSession.type = 'playback'; } catch (e) { /* 지원 안 함 */ }
const AC = window.AudioContext || window.webkitAudioContext;
const ctx = AC ? new AC() : null;
const buffers = {};
function loadSound(name) {
  if (!ctx) return;
  fetch(`sounds/${name}.mp3`)
    .then((r) => r.arrayBuffer())
    .then((b) => new Promise((res, rej) => ctx.decodeAudioData(b, res, rej)))
    .then((buf) => { buffers[name] = buf; })
    .catch(() => { /* 실패하면 아래 Audio 대체 재생 사용 */ });
}
// 짧은 소리만 바로 준비하고, 긴 싱잉볼 소리는 처음 필요할 때 받는다 (첫 화면을 빨리 띄우기 위해)
loadSound('click');
loadSound('moktak');
let bowlRequested = false;
function needBowl() {
  if (bowlRequested) return;
  bowlRequested = true;
  loadSound('bowl');
}

// 배터리 절약: 소리가 끝나고 한동안 조용하면 오디오 엔진을 잠재운다
let idleTimer = null;
function sleepAudioLater(seconds) {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(() => { if (ctx && ctx.state === 'running') ctx.suspend().catch(() => {}); }, (seconds + 15) * 1000);
}

function unlockAudio() {
  if (ctx && ctx.state !== 'running') ctx.resume().catch(() => {});
}
['pointerdown', 'touchend', 'click', 'keydown'].forEach((ev) => document.addEventListener(ev, unlockAudio, true));

function play(name, volume = 1) {
  if (!S.settings.sound) return;
  if (name === 'bowl') needBowl();
  unlockAudio();
  const buf = buffers[name];
  if (ctx && buf) {
    const src = ctx.createBufferSource();
    const gain = ctx.createGain();
    gain.gain.value = volume;
    src.buffer = buf;
    src.connect(gain).connect(ctx.destination);
    src.start();
    sleepAudioLater(buf.duration);
  } else {
    const a = new Audio(`sounds/${name}.mp3`);
    a.volume = volume;
    a.play().catch(() => {});
  }
}

/* ───────── 진동 ───────── */
const iosSwitch = document.querySelector('.ios-haptic');
function haptic(pattern) {
  if (!S.settings.haptic) return;
  if (typeof navigator.vibrate === 'function') {
    navigator.vibrate(pattern);
  } else if (iosSwitch) {
    // 아이폰(iOS 18 이상): 숨은 스위치를 누르면 시스템 햅틱이 한 번 온다
    const n = Array.isArray(pattern) ? Math.ceil(pattern.length / 2) : 1;
    for (let i = 0; i < n; i++) setTimeout(() => iosSwitch.click(), i * 140);
  }
}

/* 누르자마자 반응하도록 pointerdown 사용. 키보드(Enter/Space)도 지원 */
function onTap(el, fn) {
  el.tabIndex = 0;
  el.addEventListener('pointerdown', (e) => {
    if (e.button > 0) return;
    if (e.target.closest('button, input, label, a')) return;
    fn(e);
  });
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); }
  });
}
function flash(el, cls, ms) {
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove(cls), ms);
}

/* ───────── 탭 ───────── */
const views = { beads: $('#view-beads'), moktak: $('#view-moktak'), bowl: $('#view-bowl'), temple: $('#view-temple') };
function showTab(name) {
  if (!views[name]) name = 'beads';
  for (const [k, v] of Object.entries(views)) v.hidden = k !== name;
  document.querySelectorAll('#tabs button').forEach((b) => {
    if (b.dataset.view === name) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  $('#title').textContent = views[name].dataset.title;
  S.tab = name;
  save();
  if (name === 'bowl') needBowl();
}
document.querySelectorAll('#tabs button').forEach((b) => b.addEventListener('click', () => showTab(b.dataset.view)));

/* ───────── 1. 염주 ───────── */
const ring = $('#mala-ring');
const SVGNS = 'http://www.w3.org/2000/svg';
const RADIUS = 132;
let spinOffset = 0; // 한 바퀴를 넘길 때 뒤로 감기지 않도록 누적하는 각도

function beadState() { return S.beads[S.beads.mode]; }
function stepDeg() { return 360 / (S.beads.mode + 1); } // +1은 모주(가장 큰 구슬) 자리

function buildMala() {
  const n = S.beads.mode;
  const step = (2 * Math.PI) / (n + 1);
  const r = n === 21 ? 12.5 : 3.8;
  ring.replaceChildren();
  const cord = document.createElementNS(SVGNS, 'circle');
  cord.setAttribute('r', RADIUS);
  cord.setAttribute('class', 'cord');
  cord.setAttribute('stroke-width', n === 21 ? 1.6 : 0.8);
  ring.appendChild(cord);
  // 구슬 이미지는 가운데 80%에 구슬이 있으므로 1.25배 크기로 놓는다.
  // 나뭇결(구멍 방향)이 줄을 따라가도록 각 구슬을 자기 자리 각도만큼 돌린다.
  const place = (href, i, radius) => {
    const img = document.createElementNS(SVGNS, 'image');
    const size = radius * 2 * 1.25;
    img.setAttribute('href', href);
    img.setAttribute('x', -size / 2);
    img.setAttribute('y', -size / 2);
    img.setAttribute('width', size);
    img.setAttribute('height', size);
    img.setAttribute('transform', `rotate(${(i * step * 180) / Math.PI}) translate(0 ${-RADIUS})`);
    ring.appendChild(img);
  };
  // 구슬 i는 모주에서 시계 방향으로 i칸. 링을 돌려 지금 구슬을 맨 위 표시(▼) 아래로 가져온다
  for (let i = 1; i <= n; i++) place('images/bead.webp', i, r);
  place('images/head.webp', 0, n === 21 ? 16 : 7);
  spinOffset = 0;
  renderBeads(false);
}

function renderBeads(animate = true) {
  const n = S.beads.mode;
  const st = beadState();
  ring.classList.toggle('no-anim', !animate);
  ring.style.transform = `rotate(${spinOffset - st.count * stepDeg()}deg)`;
  if (!animate) { void ring.getBoundingClientRect(); }
  $('#bead-count').textContent = st.count;
  $('#bead-sub').textContent = st.count === n ? '한 바퀴 원만' : `${n} 중`;
  const t = S.beads.days[today()] || 0;
  $('#bead-stats').textContent = st.rounds ? `${st.rounds}바퀴 · 오늘 ${t}바퀴` : (t ? `오늘 ${t}바퀴` : '');
  document.querySelectorAll('#bead-mode button').forEach((b) => b.setAttribute('aria-checked', String(+b.dataset.n === n)));
  $('#bead-reset .label').textContent = st.count > 0 ? '길게 눌러 이번 바퀴 초기화' : (st.rounds > 0 ? '길게 눌러 바퀴 수 초기화' : '');
  $('#bead-reset').hidden = st.count === 0 && st.rounds === 0;
}

onTap($('#bead-tap'), () => {
  const n = S.beads.mode;
  const st = beadState();
  if (st.count >= n) {
    st.count = 0;
    spinOffset -= 360; // 모주를 지나 앞으로 계속 돌도록
  }
  st.count += 1;
  if (S.settings.click) play('click', 0.55);
  if (st.count === n) {
    st.rounds += 1;
    const d = today();
    S.beads.days[d] = (S.beads.days[d] || 0) + 1;
    play('bowl', 0.6);
    haptic([40, 70, 40, 70, 40]);
    flash($('.count-box'), 'pulse', 900);
    flash($('#round-pop'), 'show', 1400);
  } else {
    haptic(8);
  }
  save();
  renderBeads(true);
});

document.querySelectorAll('#bead-mode button').forEach((b) => b.addEventListener('click', () => {
  const n = +b.dataset.n;
  if (n === S.beads.mode) return;
  S.beads.mode = n; // 21개·108개는 각각 따로 세어 두므로 바꿔도 숫자가 사라지지 않음
  save();
  buildMala();
}));

// 길게 눌러 초기화 (실수로 지워지지 않게)
(() => {
  const btn = $('#bead-reset');
  let timer = null;
  const cancel = () => { clearTimeout(timer); timer = null; btn.classList.remove('holding'); };
  btn.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    btn.classList.add('holding');
    timer = setTimeout(() => {
      cancel();
      const st = beadState();
      if (st.count > 0) st.count = 0;
      else st.rounds = 0;
      spinOffset = 0;
      haptic(30);
      save();
      renderBeads(false);
    }, 1000);
  });
  ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => btn.addEventListener(ev, cancel));
  btn.addEventListener('contextmenu', (e) => e.preventDefault());
})();

/* ───────── 소원 (염주 화면 위에 고정) ───────── */
const wishDialog = $('#wish-dialog');
const wishForm = $('#wish-form');
function renderWish() {
  const w = (S.wish || '').trim();
  $('#wish-text').textContent = w || '✎ 눌러서 나의 소원 적기';
  $('#wish').classList.toggle('empty', !w);
}
$('#wish').addEventListener('click', () => {
  wishForm.elements.wish.value = S.wish || '';
  wishDialog.returnValue = '';
  wishDialog.showModal();
});
wishDialog.addEventListener('close', () => {
  if (wishDialog.returnValue !== 'save') return;
  S.wish = wishForm.elements.wish.value.trim();
  save();
  renderWish();
});

/* ───────── 2. 목탁 ───────── */
onTap($('#moktak-tap'), () => {
  play('moktak');
  haptic(12);
  flash($('#moktak-mallet'), 'strike', 70);
  flash($('#moktak-art'), 'hit', 110);
});

/* ───────── 3. 싱잉볼 ───────── */
onTap($('#bowl-tap'), () => {
  play('bowl');
  haptic(20);
  flash($('#bowl-mallet'), 'strike', 70);
  flash($('#bowl-art'), 'hit', 160);
});

// 타이머: 'N분짜리 소리 파일(종 한 번 + 무음)'을 반복 재생한다.
// 코드 타이머는 화면이 꺼지면 멈추지만, 재생 중인 소리는 계속 나므로 끊기지 않는다.
let timerAudio = null;
let running = false;
let wakeLock = null;
let tick = null;

function renderBowl() {
  document.querySelectorAll('#bowl-interval button').forEach((b) => b.setAttribute('aria-checked', String(+b.dataset.m === S.bowl.interval)));
  $('#bowl-start').textContent = running ? '정지' : '시작';
  $('#bowl-wake').checked = !!S.bowl.wake;
}
function fmt(sec) {
  sec = Math.max(0, Math.ceil(sec));
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`;
}
function updateCountdown() {
  const el = $('#bowl-countdown');
  if (!running || !timerAudio || document.hidden) return; // 화면이 꺼져 있으면 계산 안 함 (배터리 절약)
  const d = timerAudio.duration;
  el.textContent = isFinite(d) && d > 0 ? `다음 종까지 ${fmt(d - timerAudio.currentTime)}` : '준비 중…';
}

async function requestWake() {
  if (!running || !S.bowl.wake || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
  try { wakeLock = await navigator.wakeLock.request('screen'); } catch (e) { wakeLock = null; }
}
function releaseWake() {
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
}
document.addEventListener('visibilitychange', () => { requestWake(); updateCountdown(); });

function startTimer() {
  stopTimer(true);
  const m = S.bowl.interval;
  const audio = new Audio(`sounds/bowl-${m}m.mp3`);
  timerAudio = audio;
  audio.loop = true;
  audio.volume = S.settings.sound ? 1 : 0;
  audio.addEventListener('pause', () => {
    // 전화 등으로 시스템이 소리를 멈춘 경우 화면도 멈춤으로 바꾼다
    if (running && timerAudio === audio) { stopTimer(true); $('#bowl-countdown').textContent = '멈췄습니다'; }
  });
  running = true;
  timerAudio.play().catch(() => {
    stopTimer(true);
    $('#bowl-countdown').textContent = '소리를 재생할 수 없습니다';
  });
  if ('mediaSession' in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: `싱잉볼 · ${m}분 간격`,
        artist: '합장',
        artwork: [{ src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' }],
      });
      navigator.mediaSession.setActionHandler('play', startTimer);
      navigator.mediaSession.setActionHandler('pause', () => stopTimer());
      navigator.mediaSession.setActionHandler('stop', () => stopTimer());
    } catch (e) { /* 일부 기능 미지원 */ }
  }
  tick = setInterval(updateCountdown, 1000);
  updateCountdown();
  requestWake();
  renderBowl();
}
function stopTimer(silent) {
  running = false;
  clearInterval(tick);
  if (timerAudio) {
    const a = timerAudio;
    timerAudio = null;
    a.pause();
    a.removeAttribute('src');
    a.load();
  }
  releaseWake();
  if (!silent) $('#bowl-countdown').innerHTML = '&nbsp;';
  renderBowl();
}

$('#bowl-start').addEventListener('click', () => (running ? stopTimer() : startTimer()));
document.querySelectorAll('#bowl-interval button').forEach((b) => b.addEventListener('click', () => {
  S.bowl.interval = +b.dataset.m;
  save();
  if (running) startTimer();
  else renderBowl();
}));
if (!('wakeLock' in navigator)) $('#bowl-wake').closest('label').hidden = true;
$('#bowl-wake').addEventListener('change', (e) => {
  S.bowl.wake = e.target.checked;
  save();
  if (S.bowl.wake) requestWake();
  else releaseWake();
});

/* ───────── 4. 사찰 ───────── */
function kakaoSearch(name) {
  window.open(`https://map.kakao.com/link/search/${encodeURIComponent(name)}`, '_blank', 'noopener');
}
$('#temple-search').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('#temple-q').value.trim();
  if (!q) { $('#temple-q').focus(); return; }
  kakaoSearch(q);
});

function knownNames() {
  const set = new Set();
  S.favs.forEach((f) => f && set.add(f));
  S.visits.forEach((v) => set.add(v.name));
  return [...set];
}
function el(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  Object.assign(e, props);
  e.append(...kids);
  return e;
}

function renderFavs() {
  const ol = $('#favs');
  ol.replaceChildren();
  S.favs.forEach((name, i) => {
    const li = el('li', {}, el('span', { className: 'rank', textContent: i + 1 }));
    if (name) {
      li.append(
        el('span', { className: 'name', textContent: name }),
        el('button', { className: 'text-btn', textContent: '지도', onclick: () => kakaoSearch(name) }),
        el('button', { className: 'text-btn', textContent: '변경', onclick: () => openFav(i) }),
      );
    } else {
      li.append(
        el('span', { className: 'name empty', textContent: '비어 있음' }),
        el('button', { className: 'text-btn', textContent: '지정', onclick: () => openFav(i) }),
      );
    }
    ol.append(li);
  });
}

function renderVisits() {
  const ul = $('#visits');
  ul.replaceChildren();
  const list = [...S.visits].sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));
  if (!list.length) {
    ul.append(el('li', { className: 'none', textContent: '아직 기록이 없습니다.' }));
    return;
  }
  for (const v of list) {
    const li = el('li', { onclick: () => openVisit(v.id) },
      el('div', { className: 'meta' },
        el('span', { className: 'name', textContent: v.name }),
        el('span', { className: 'date', textContent: v.date.replaceAll('-', '. ') })),
    );
    if (v.wish) li.append(el('div', { className: 'v-wish', textContent: v.wish }));
    ul.append(li);
  }
}

function renderNameList() {
  let dl = $('#temple-names');
  if (!dl) { dl = el('datalist', { id: 'temple-names' }); document.body.append(dl); }
  dl.replaceChildren(...knownNames().map((n) => el('option', { value: n })));
}

// 자주 가는 절 지정
const favDialog = $('#fav-dialog');
const favForm = $('#fav-form');
favForm.elements.name.setAttribute('list', 'temple-names');
favForm.elements.name.required = false;
let favIndex = 0;
function openFav(i) {
  favIndex = i;
  renderNameList();
  $('#fav-dialog-title').textContent = `${i + 1}순위 절`;
  favForm.elements.name.value = S.favs[i] || '';
  favForm.elements.name.placeholder = '비우면 지정이 해제됩니다';
  favDialog.returnValue = '';
  favDialog.showModal();
}
favDialog.addEventListener('close', () => {
  if (favDialog.returnValue !== 'save') return;
  S.favs[favIndex] = favForm.elements.name.value.trim() || null;
  save();
  renderFavs();
});

// 방문 기록
const visitDialog = $('#visit-dialog');
const visitForm = $('#visit-form');
visitForm.elements.name.setAttribute('list', 'temple-names');
let editingId = null;
function openVisit(id) {
  editingId = id || null;
  const v = S.visits.find((x) => x.id === id);
  renderNameList();
  $('#visit-dialog-title').textContent = v ? '방문 기록 수정' : '방문 기록';
  visitForm.elements.name.value = v ? v.name : '';
  visitForm.elements.date.value = v ? v.date : today();
  visitForm.elements.wish.value = v ? v.wish : S.wish;
  $('#visit-delete').hidden = !v;
  visitDialog.returnValue = '';
  visitDialog.showModal();
}
$('#visit-add').addEventListener('click', () => openVisit(null));
visitDialog.addEventListener('close', () => {
  if (visitDialog.returnValue !== 'save') return;
  const data = {
    name: visitForm.elements.name.value.trim(),
    date: visitForm.elements.date.value,
    wish: visitForm.elements.wish.value.trim(),
  };
  if (!data.name || !data.date) return;
  const v = S.visits.find((x) => x.id === editingId);
  if (v) Object.assign(v, data);
  else S.visits.push({ id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6), ...data });
  save();
  renderVisits();
});
$('#visit-delete').addEventListener('click', () => {
  if (!confirm('이 기록을 삭제할까요?')) return;
  S.visits = S.visits.filter((x) => x.id !== editingId);
  save();
  renderVisits();
  visitDialog.close('delete');
});

/* ───────── 설정 · 백업 ───────── */
const settingsDialog = $('#settings-dialog');
$('#open-settings').addEventListener('click', () => {
  $('#set-sound').checked = S.settings.sound;
  $('#set-haptic').checked = S.settings.haptic;
  $('#set-click').checked = S.settings.click;
  settingsDialog.showModal();
});
$('#set-sound').addEventListener('change', (e) => {
  S.settings.sound = e.target.checked;
  if (timerAudio) timerAudio.volume = S.settings.sound ? 1 : 0;
  save();
});
$('#set-haptic').addEventListener('change', (e) => { S.settings.haptic = e.target.checked; save(); });
$('#set-click').addEventListener('change', (e) => { S.settings.click = e.target.checked; save(); });

$('#backup-export').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify({ app: 'hapjang', version: 1, savedAt: new Date().toISOString(), data: S }, null, 2)], { type: 'application/json' });
  const a = el('a', { href: URL.createObjectURL(blob), download: `hapjang-backup-${today()}.json` });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
});
$('#backup-import').addEventListener('click', () => $('#backup-file').click());
$('#backup-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  try {
    const json = JSON.parse(await file.text());
    if (!json || json.app !== 'hapjang' || typeof json.data !== 'object') throw new Error('형식 오류');
    if (!confirm('지금 기록을 백업 파일의 내용으로 바꿀까요?')) return;
    S = merge(DEFAULTS, json.data);
    save();
    renderAll();
    alert('불러왔습니다.');
  } catch (err) {
    alert('백업 파일을 읽을 수 없습니다.');
  }
});

/* ───────── 시작 ───────── */
function renderAll() {
  renderWish();
  buildMala();
  renderBowl();
  renderFavs();
  renderVisits();
  showTab(S.tab);
}
renderAll();

// 날짜가 바뀌면 '오늘 ○바퀴'를 새로 표시
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') renderBeads(false); });

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  // 새 버전이 설치되면 한 번 새로고침해서 바로 보여준다 (싱잉볼 타이머가 도는 중이면 방해하지 않음)
  const hadController = !!navigator.serviceWorker.controller;
  let reloaded = false;
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController || reloaded || running) return;
    reloaded = true;
    location.reload();
  });
  // 오프라인 저장은 첫 화면이 다 뜬 뒤에 시작 (처음 열 때 다운로드가 겹치지 않도록)
  const registerSW = () => navigator.serviceWorker.register('sw.js', { updateViaCache: 'none' }).catch(() => {});
  if (document.readyState === 'complete') setTimeout(registerSW, 1500);
  else window.addEventListener('load', () => setTimeout(registerSW, 1500));
}
