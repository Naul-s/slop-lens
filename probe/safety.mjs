/**
 * The trust boundary of the probe. Whatever is being scanned is untrusted: a third-party site, or a folder
 * someone downloaded whose scripts run as soon as it is rendered.
 *
 *   launchBrowser  Chromium with its OS sandbox on (Playwright turns it off by default)
 *   serveDirs      loopback static server that cannot leave the folder and never serves secrets
 *   guardContext   network rules for a browser context, enforced below the page's JavaScript
 *   inputPolicy    what automated input may touch when the page is not on this machine
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const LOCAL_HOST = /^(localhost|127\.0\.0\.1|\[::1\]|(.+\.)?localhost)$/i;

/** A page served from this machine (the user's own build or dev server). Everything else is a third party. */
export function isLocal(url) {
  try {
    const u = new URL(url);
    if (u.protocol === 'about:' || u.protocol === 'data:') return true;
    if (u.protocol === 'blob:') return isLocal(u.origin);
    return LOCAL_HOST.test(u.hostname);
  } catch { return false; }
}

// ---------------------------------------------------------------- browser
export async function launchBrowser(chromium, extra = []) {
  // Escape hatch for containers where Chromium cannot create its sandbox. Never the silent default.
  const sandbox = process.env.SLOP_LENS_NO_SANDBOX !== '1';
  let last;
  for (const opt of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) {
    try {
      const browser = await chromium.launch({ headless: true, chromiumSandbox: sandbox, args: extra, ...opt });
      return { browser, name: opt.channel || 'chromium' };
    } catch (e) {
      if (!last || /sandbox/i.test(e.message)) last = e;
    }
  }
  const why = (last?.message || '').split('\n')[0];
  if (/sandbox/i.test(last?.message || '')) {
    throw new Error('브라우저 샌드박스를 켤 수 없음 (컨테이너·root 실행 등). 믿는 대상만 검사한다면 SLOP_LENS_NO_SANDBOX=1 로 끌 수 있음: ' + why);
  }
  throw new Error('브라우저 실행 실패 (Chrome/Edge 없음). `npx playwright-core install chromium` 실행 필요: ' + why);
}

// ---------------------------------------------------------------- static server
const SECRET = /^(id_rsa|id_dsa|id_ecdsa|id_ed25519|credentials(\.json)?|secrets?\.(json|ya?ml|toml)|service[-_]?account.*\.json)$|\.(pem|key|p12|pfx|keystore|jks|kdbx)$/i;

const inside = (base, f) => {
  const rel = path.relative(base, f);
  return rel === '' || (!rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel));
};

/** Absolute path of a file that may be served for `urlPath` under `root`, or null. */
export function resolveFile(root, urlPath) {
  const parts = urlPath.split(/[\\/]+/).filter(Boolean);
  // dot files (.env, .git, .npmrc), '..', NTFS streams and 8.3 aliases ("ENV~1") all reach files a page has no business reading
  if (parts.some(p => (p.startsWith('.') && p !== '.well-known') || /[:\0]|~\d|[. ]$/.test(p) || SECRET.test(p))) return null;
  try {
    const base = fs.realpathSync(root);
    let f = path.resolve(base, ...parts);
    if (!inside(base, f)) return null;
    if (fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
    f = fs.realpathSync(f);  // a link inside the folder may point outside it
    if (!inside(base, f) || SECRET.test(path.basename(f)) || path.relative(base, f).split(path.sep).some(p => p.startsWith('.') && p !== '.well-known')) return null;
    return fs.statSync(f).isFile() ? f : null;
  } catch { return null; }
}

/** `route(pathname)` maps a request to {root, rel}, or {body} for a synthetic page, or null. */
export function serveDirs(route, mime) {
  const srv = http.createServer((req, res) => {
    try {
      // Host check: another site must not reach this server through DNS rebinding
      const { port } = srv.address();
      if (req.headers.host !== `127.0.0.1:${port}`) { res.writeHead(403); return res.end(); }
      const hit = route(decodeURIComponent(new URL(req.url, 'http://x').pathname));
      if (hit?.body !== undefined) { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end(hit.body); }
      const f = hit ? resolveFile(hit.root, hit.rel) : null;
      if (!f) { res.writeHead(404); return res.end('not found'); }
      res.writeHead(200, { 'Content-Type': mime[path.extname(f).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(f).on('error', () => res.destroy()).pipe(res);
    } catch { res.writeHead(400); res.end(); }
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r(srv)));
}

// ---------------------------------------------------------------- network
const READ_ONLY = /^(GET|HEAD|OPTIONS)$/i;

/**
 * Rules enforced at the network layer, so they hold whatever a click or key turned out to trigger:
 *  - after automated input starts (`arm`), nothing that changes state is sent to another machine
 *    (POST/PUT/PATCH/DELETE, beacons, new WebSockets). Reading still works, so games keep loading.
 *  - service workers are blocked when the context is created, because their requests skip these routes.
 *  - `holdNavigation` keeps a self-reloading page still long enough to read it.
 */
export async function guardContext(ctx) {
  const state = { armed: false, hold: 0, blocked: 0 };
  await ctx.route('**/*', route => {
    const q = route.request();
    if (state.armed && !READ_ONLY.test(q.method()) && !isLocal(q.url())) {
      state.blocked++;
      return route.abort('blockedbyclient').catch(() => {});
    }
    if (state.hold && q.isNavigationRequest()) return route.abort('aborted').catch(() => {});
    return route.continue().catch(() => {});
  });
  await ctx.routeWebSocket(/.*/, ws => {
    if (state.armed && !isLocal(ws.url().replace(/^ws/i, 'http'))) { state.blocked++; ws.close(); return; }
    ws.connectToServer();
  });
  return {
    arm() { state.armed = true; },
    get blocked() { return state.blocked; },
    async holdNavigation(fn) {
      state.hold++;
      try { return await fn(); } finally { state.hold--; }
    },
  };
}

// ---------------------------------------------------------------- automated input
// On a third-party page only a label that can mean nothing but "play" is clicked: the whole text must match.
const PLAY_ONLY = /^(▶\s*)?(play|play now|play game|start|start game|new game|tap to start|click to start|플레이|시작|시작하기|게임 시작|게임 시작하기)(\s*[!▶])?$/i;
// keys that activate whatever has focus
const ACTIVATING = new Set(['Enter', 'Space']);

/**
 * All gameplay input goes through here. Local pages get everything; on any other host (including one a local
 * page navigated to) clicks land only on the game canvas and keys only where they cannot press a control.
 */
export function inputPolicy(page) {
  const free = () => isLocal(page.url());
  const skipped = { n: 0 };

  async function canClick(x, y) {
    if (free()) return true;
    const ok = await page.evaluate(([px, py]) => {
      const el = document.elementFromPoint(px, py);
      return !!el && el.tagName === 'CANVAS' && !el.closest('a,button,form,[role=button]');
    }, [x, y]).catch(() => false);
    if (!ok) skipped.n++;
    return ok;
  }

  async function canPress(key) {
    if (free()) return true;
    const focus = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body || el === document.documentElement || el.tagName === 'CANVAS') return 'game';
      if (el.closest('form') || el.isContentEditable || /^(INPUT|TEXTAREA|SELECT|IFRAME)$/.test(el.tagName)) return 'field';
      return 'control';
    }).catch(() => 'field');
    const ok = focus === 'game' || (focus === 'control' && !ACTIVATING.has(key));
    if (!ok) skipped.n++;
    return ok;
  }

  return {
    skipped,
    free,
    async click(x, y) {
      if (!(await canClick(x, y))) return false;
      await page.mouse.click(x, y);
      return true;
    },
    async press(key, holdMs = 0) {
      if (!(await canPress(key))) return false;
      if (!holdMs) { await page.keyboard.press(key); return true; }
      await page.keyboard.down(key);
      await page.waitForTimeout(holdMs);
      await page.keyboard.up(key);
      return true;
    },
    /** Mark the start-like button that may be clicked and return its label. */
    async markStartButton(menuRx, riskyRx) {
      const rx = free() ? menuRx : PLAY_ONLY;
      return page.evaluate(({ src, risky, strict }) => {
        const re = new RegExp(src, 'i'), rk = new RegExp(risky, 'i');
        const text = b => String(b.innerText ?? b.textContent ?? b.value ?? '').trim();
        const vis = el => {
          const r = el.getBoundingClientRect(), s = getComputedStyle(el);
          return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none';
        };
        const el = [...document.querySelectorAll('button,[role=button],a,input[type=button]')].filter(vis).find(b => {
          const t = text(b);
          if (!re.test(t) || rk.test(t)) return false;
          if (!strict) return true;
          // links navigate, forms submit, consent/age gates accept terms: none of those are ours to press
          return !b.closest('a[href],form,[id*=cookie i],[class*=cookie i],[id*=consent i],[class*=consent i],[id*=gdpr i],[class*=gdpr i],[id*=terms i],[class*=terms i]');
        });
        if (!el) return null;
        el.setAttribute('data-sl-start', '1');
        return text(el).replace(/\s+/g, ' ').slice(0, 30);
      }, { src: rx.source, risky: riskyRx.source, strict: !free() }).catch(() => null);
    },
  };
}
