// 오프라인에서도 앱이 열리도록 파일을 휴대폰에 저장해 두는 서비스 워커.
// 앱 파일을 고친 뒤에는 VERSION 숫자를 올려야 사용자 휴대폰에 새 버전이 반영된다.
const VERSION = 'v3';
const CORE = `hapjang-core-${VERSION}`;
const LONG = `hapjang-long-${VERSION}`; // 타이머용 긴 소리 파일 (처음 쓸 때 저장)
const FONTS = 'hapjang-fonts';

const CORE_FILES = [
  './',
  'index.html',
  'style.css',
  'app.js',
  'manifest.webmanifest',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/apple-touch-icon.png',
  'sounds/click.mp3',
  'sounds/moktak.mp3',
  'sounds/bowl.mp3',
  'images/bead.png',
  'images/head.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CORE).then((c) => c.addAll(CORE_FILES)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => (k.startsWith('hapjang-core-') && k !== CORE) || (k.startsWith('hapjang-long') && k !== LONG)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// 아이폰 Safari는 소리 파일을 '일부분(Range)'씩 요청하므로 저장된 파일에서 잘라서 돌려준다
async function rangeResponse(request, cached) {
  const range = request.headers.get('range');
  if (!range) return cached;
  const buf = await cached.arrayBuffer();
  const m = /bytes=(\d*)-(\d*)/.exec(range);
  let start = m && m[1] ? Number(m[1]) : 0;
  let end = m && m[2] ? Number(m[2]) : buf.byteLength - 1;
  if (m && !m[1] && m[2]) { start = buf.byteLength - Number(m[2]); end = buf.byteLength - 1; }
  end = Math.min(end, buf.byteLength - 1);
  return new Response(buf.slice(start, end + 1), {
    status: 206,
    headers: {
      'Content-Type': 'audio/mpeg',
      'Content-Range': `bytes ${start}-${end}/${buf.byteLength}`,
      'Content-Length': String(end - start + 1),
      'Accept-Ranges': 'bytes',
    },
  });
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  // 글꼴: 한 번 받으면 저장해 두고 사용
  if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') {
    e.respondWith(caches.open(FONTS).then(async (c) => {
      const hit = await c.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok || res.type === 'opaque') c.put(req, res.clone());
      return res;
    }));
    return;
  }
  if (url.origin !== location.origin) return;

  // 타이머용 긴 소리: 저장돼 있으면 사용, 없으면 인터넷에서 재생하면서 뒤에서 통째로 저장
  if (/\/sounds\/bowl-\d+m\.mp3$/.test(url.pathname)) {
    e.respondWith((async () => {
      const c = await caches.open(LONG);
      const hit = await c.match(url.pathname);
      if (hit) return rangeResponse(req, hit);
      e.waitUntil(fetch(url.pathname).then((res) => res.ok && c.put(url.pathname, res)).catch(() => {}));
      return fetch(req);
    })());
    return;
  }

  // 소리·그림: 잘 안 바뀌고 크기가 있으니 저장된 것을 먼저 쓴다
  if (/\.(mp3|png)$/.test(url.pathname)) {
    e.respondWith(
      caches.match(req, { ignoreSearch: true }).then((hit) => {
        if (hit) return req.headers.get('range') && url.pathname.endsWith('.mp3') ? rangeResponse(req, hit) : hit;
        return fetch(req);
      }),
    );
    return;
  }

  // 화면·코드(html, css, js): 인터넷에서 최신 것을 먼저 받고, 안 되면(오프라인) 저장된 것을 쓴다.
  // 이렇게 해야 앱을 고쳤을 때 휴대폰에 바로 반영된다.
  e.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CORE).then((c) => c.put(req, copy));
        }
        return res;
      })
      .catch(() => caches.match(req, { ignoreSearch: true })),
  );
});
