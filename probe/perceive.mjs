#!/usr/bin/env node
/**
 * SlopLens asset perception — analyzes what people SEE and HEAR in a project's assets.
 *
 *   node perceive.mjs --spec spec.json
 *
 * spec.json = {
 *   "roots":  { "a": "D:/Project", "s": "C:/Temp/shots" },        // served as /a/..., /s/...
 *   "images": ["a/Assets/Icons/Fire.png", ...],                    // sprites, icons, UI art
 *   "audio":  ["a/Assets/Sound/Hit.wav", ...],                     // wav / mp3 / ogg
 *   "frames": ["s/game-0-start.png", ...],                         // screenshots / gameplay frames
 *   "out":    "C:/Temp/perception"
 * }
 * Prints one JSON object: per-asset features + contact-sheet image paths for the visual review.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') && a.push([v.slice(2), all[i + 1]]), a), []));
const emit = o => process.stdout.write(JSON.stringify(o));
let chromium;
try { ({ chromium } = await import('playwright-core')); } catch { emit({ ok: false, error: 'playwright-core 미설치' }); process.exit(0); }

const spec = JSON.parse(fs.readFileSync(args.spec, 'utf8'));
const LIB = fs.readFileSync(path.join(here, 'analysis-lib.js'), 'utf8');
const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif', '.bmp': 'image/bmp',
  '.tga': 'application/octet-stream', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.html': 'text/html; charset=utf-8' };

const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (u === '/' || u === '/blank') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); return res.end('<!doctype html><meta charset=utf-8><body style="margin:0;background:#20202a">'); }
  const [, key, ...rest] = u.split('/');
  const root = spec.roots[key];
  if (!root) { res.writeHead(404); return res.end(); }
  const base = path.resolve(root), f = path.resolve(base, rest.join('/'));
  if (!f.startsWith(base) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(f).toLowerCase()] || 'application/octet-stream', 'Access-Control-Allow-Origin': '*' });
  fs.createReadStream(f).pipe(res);
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const origin = `http://127.0.0.1:${server.address().port}`;

let browser;
for (const opt of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) { try { browser = await chromium.launch({ headless: true, ...opt }); break; } catch {} }
if (!browser) { emit({ ok: false, error: '브라우저 실행 실패' }); process.exit(0); }
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.addInitScript({ content: LIB });
await page.goto(origin + '/blank');

const out = { ok: true, images: [], audio: [], sheets: {} };
fs.mkdirSync(spec.out, { recursive: true });

// ---------------- images
for (const rel of spec.images || []) {
  const r = await page.evaluate(async url => {
    try {
      const img = new Image(); img.src = url; await img.decode();
      const W = img.naturalWidth, H = img.naturalHeight, s = Math.min(1, 1600 / Math.max(W, H));
      const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(W * s)); c.height = Math.max(1, Math.round(H * s));
      const g = c.getContext('2d'); g.imageSmoothingEnabled = false; g.drawImage(img, 0, 0, c.width, c.height);
      const f = window.__slLib.imageFeatures(g.getImageData(0, 0, c.width, c.height));
      f.w = W; f.h = H; return f;
    } catch (e) { return { error: String(e).slice(0, 120) }; }
  }, `${origin}/${rel}`).catch(e => ({ error: String(e).slice(0, 120) }));
  out.images.push({ path: rel, ...r });
}

// ---------------- audio
for (const rel of spec.audio || []) {
  const r = await page.evaluate(async url => {
    try {
      const ab = await (await fetch(url)).arrayBuffer();
      const ctx = new OfflineAudioContext(1, 1, 44100);
      const buf = await ctx.decodeAudioData(ab);
      const n = Math.min(buf.length, buf.sampleRate * 90), mono = new Float32Array(n);
      for (let c = 0; c < buf.numberOfChannels; c++) { const d = buf.getChannelData(c); for (let i = 0; i < n; i++) mono[i] += d[i] / buf.numberOfChannels; }
      const f = window.__slLib.audioFeatures(mono, buf.sampleRate); f.fullDuration = +buf.duration.toFixed(2); f.channels = buf.numberOfChannels; return f;
    } catch (e) { return { error: String(e).slice(0, 120) }; }
  }, `${origin}/${rel}`).catch(e => ({ error: String(e).slice(0, 120) }));
  out.audio.push({ path: rel, ...r });
}

// ---------------- screen color schemes (each screenshot / gameplay frame)
out.frames = [];
for (const rel of spec.frames || []) {
  const r = await page.evaluate(async url => {
    try {
      const img = new Image(); img.src = url; await img.decode();
      const W = img.naturalWidth, H = img.naturalHeight, s = Math.min(1, 480 / W);
      const c = document.createElement('canvas'); c.width = Math.max(1, Math.round(W * s)); c.height = Math.max(1, Math.round(Math.min(H, W * 1.2) * s));
      const g = c.getContext('2d'); g.drawImage(img, 0, 0, W, Math.min(H, W * 1.2), 0, 0, c.width, c.height);   // first screen only for tall pages
      const f = window.__slLib.screenFeatures(g.getImageData(0, 0, c.width, c.height)); f.w = W; f.h = H; return f;
    } catch (e) { return { error: String(e).slice(0, 120) }; }
  }, `${origin}/${rel}`).catch(e => ({ error: String(e).slice(0, 120) }));
  out.frames.push({ path: rel, ...r });
}

// ---------------- slices: tall full-page captures become screen-sized pieces a reviewer can actually read
out.slices = [];
for (const rel of spec.frames || []) {
  const parts = await page.evaluate(async url => {
    const img = new Image(); img.src = url; await img.decode();
    const W = img.naturalWidth, H = img.naturalHeight, step = Math.round(W * 0.625);
    if (H <= W * 1.6) return [];
    const res = [];
    for (let y = 0, k = 0; y < H && k < 14; y += step, k++) {
      const h = Math.min(step, H - y); if (h < 80) break;
      const c = document.createElement('canvas'); c.width = W; c.height = h;
      c.getContext('2d').drawImage(img, 0, y, W, h, 0, 0, W, h);
      res.push({ y, data: c.toDataURL('image/png').split(',')[1] });
    }
    return res;
  }, `${origin}/${rel}`).catch(() => []);
  for (const [k, p] of parts.entries()) {
    const f = path.join(spec.out, `slice-${path.basename(rel, '.png')}-${String(k + 1).padStart(2, '0')}.png`);
    fs.writeFileSync(f, Buffer.from(p.data, 'base64'));
    out.slices.push({ of: rel, y: p.y, file: f });
  }
}

// ---------------- contact sheets (one image the reviewing agent can look at)
async function sheet(name, items, cell, cols, pixelated, title) {
  if (!items.length) return null;
  const html = `<!doctype html><meta charset=utf-8><style>
    body{margin:0;background:#1b1b22;color:#ddd;font:12px/1.3 system-ui,sans-serif}
    h1{font-size:15px;margin:10px 12px;color:#fff}
    .g{display:grid;grid-template-columns:repeat(${cols},${cell}px);gap:8px;padding:0 12px 12px}
    figure{margin:0;background:repeating-conic-gradient(#2b2b35 0 25%,#33333f 0 50%) 0 0/16px 16px;border:1px solid #444}
    img{display:block;width:${cell}px;height:${Math.round(cell * (pixelated ? 1 : 0.5625))}px;object-fit:contain;${pixelated ? 'image-rendering:pixelated;' : ''}}
    figcaption{padding:3px 4px;background:#111;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  </style><h1>${title}</h1><div class=g>${items.map((p, i) => `<figure><img src="${origin}/${p}"><figcaption>${i + 1}. ${p.split('/').pop()}</figcaption></figure>`).join('')}</div>`;
  const f = path.join(spec.out, `${name}.html`);
  fs.writeFileSync(f, html);
  await page.setViewportSize({ width: cols * (cell + 8) + 24, height: 120 });
  await page.setContent(html, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  const png = path.join(spec.out, `${name}.png`);
  await page.screenshot({ path: png, fullPage: true });
  return png;
}
try {
  out.sheets.assets = await sheet('asset-sheet', (spec.images || []).slice(0, 48), 128, 8, true, `에셋 시트 — 아이콘·스프라이트 ${Math.min(48, (spec.images || []).length)}개 (스타일 일관성·AI 아티팩트 판정용)`);
  out.sheets.frames = await sheet('frame-sheet', (spec.frames || []).slice(0, 9), 420, 3, false, '화면 시트 — 실제 화면/플레이 프레임');
} catch (e) { out.sheetError = String(e).slice(0, 160); }

await browser.close(); server.close();
emit(out);
process.exit(0);
