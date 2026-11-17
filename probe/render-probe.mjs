#!/usr/bin/env node
/**
 * SlopLens render probe — opens the target in a real (headless) browser and MEASURES
 * what static analysis can only guess:
 *   - computed styles: gradients by actual hue, rendered fonts, radius/shadow/glass/blob usage
 *   - WCAG text contrast against the real background
 *   - card-row uniformity and centered-text share measured from layout boxes
 *   - mobile (390px): horizontal overflow, tiny tap targets, tiny text
 *   - keyboard focus visibility (real Tab presses)
 *   - dead clicks: clicks every visible button/link and checks whether ANYTHING happens
 *   - runtime dialogs, console errors, broken resources
 *   - games: frame timing, canvas draw-call profile, audio calls, palette, reloads, emoji sprites
 *   - screenshots (desktop, full page, mobile, gameplay) for the visual-review rubric
 *
 * Usage:
 *   node render-probe.mjs --url https://site            [--out DIR] [--kind auto|web|game]
 *   node render-probe.mjs --root ./project --entry index.html [--out DIR]
 * Prints one JSON object to stdout. Never throws: failures come back as {ok:false,error}.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : 'true']);
    return acc;
  }, [])
);
const KIND = args.kind || 'auto';
const OUT = args.out || null;
const MAX_CLICKS = +(args.clicks || 12);
const PLAY_MS = +(args.play || 8000);
// On third-party sites never submit forms, buy, sign up, log in, download or accept consent.
const REMOTE = !!args.url && !/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:|\/|$)/i.test(args.url);
const RISKY = /(구매|결제|주문|장바구니|담기|cart|buy|checkout|order|pay|subscribe|구독|sign ?up|가입|회원|log ?in|로그인|delete|삭제|accept|agree|동의|수락|허용|allow|cookie|쿠키|download|다운로드|설치|install|신청|예약|book)/i;
const t0 = Date.now();
const BUDGET_MS = +(args.budget || 100000);  // return partial results instead of being killed
const overBudget = () => Date.now() - t0 > BUDGET_MS;
async function go(page, url, first = false) {
  // Heavy sites (streaming video) may never fire 'load'; DOM ready + a short settle is enough.
  try { await page.goto(url, { waitUntil: first ? 'load' : 'domcontentloaded', timeout: first ? 30000 : 15000 }); }
  catch (e) { if (!/Timeout/i.test(e.message)) throw e; }
  await page.waitForTimeout(first ? 300 : 500);
  // client-side redirects (locale, consent, A/B) replace the page right after load — wait until the URL settles
  for (let i = 0; i < 3; i++) {
    const u = page.url();
    await page.waitForTimeout(700);
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    if (page.url() === u) break;
  }
}
async function safeEval(page, fn, arg) {
  try { return await page.evaluate(fn, arg); }
  catch (e) {
    if (!/context was destroyed|navigation/i.test(e.message)) throw e;
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await page.waitForTimeout(1200);
    return await page.evaluate(fn, arg);
  }
}

function emit(obj) {
  process.stdout.write(JSON.stringify(obj));
}

let chromium;
try {
  ({ chromium } = await import('playwright-core'));
} catch {
  try { ({ chromium } = await import('playwright')); } catch {
    emit({ ok: false, error: 'playwright-core 미설치: SlopLens 폴더에서 `npm install` 을 실행하세요.' });
    process.exit(0);
  }
}

// ---------------------------------------------------------------- static server
const LIB = fs.readFileSync(new URL('./analysis-lib.js', import.meta.url), 'utf8');
const MIME = { '.html': 'text/html; charset=utf-8', '.htm': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.avif': 'image/avif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.wav': 'audio/wav', '.mp3': 'audio/mpeg',
  '.ogg': 'audio/ogg', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.wasm': 'application/wasm', '.txt': 'text/plain' };

function serve(root) {
  const base = path.resolve(root);
  const srv = http.createServer((req, res) => {
    try {
      let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      let f = path.resolve(base, '.' + p);
      if (!f.startsWith(base)) { res.writeHead(403); return res.end(); }
      if (fs.existsSync(f) && fs.statSync(f).isDirectory()) f = path.join(f, 'index.html');
      if (!fs.existsSync(f)) { res.writeHead(404); return res.end('not found'); }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(f).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(f).pipe(res);
    } catch { res.writeHead(500); res.end(); }
  });
  return new Promise(r => srv.listen(0, '127.0.0.1', () => r(srv)));
}

async function launch() {
  let last;
  for (const opt of [{ channel: 'chrome' }, { channel: 'msedge' }, {}]) {
    try {
      const b = await chromium.launch({ headless: true, ...opt, args: ['--autoplay-policy=no-user-gesture-required'] });
      return { browser: b, name: opt.channel || 'chromium' };
    } catch (e) { last = e; }
  }
  throw new Error('브라우저 실행 실패 (Chrome/Edge 없음). `npx playwright-core install chromium` 실행 필요: ' + (last?.message || '').split('\n')[0]);
}

// ---------------------------------------------------------------- in-page instrumentation
const INSTRUMENT = () => {
  const S = (window.__sl = { raf: [], intervals: [], audio: 0, dialogs: [], draw: {}, emojiText: 0, alpha: 0, shadows: 0, small: [], cur: 0 });
  const now = () => performance.now();
  const raf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = cb => raf(t => {
    S.raf.push(now()); if (S.raf.length > 4000) S.raf.shift();
    S.small.push(S.cur); if (S.small.length > 4000) S.small.shift(); S.cur = 0;
    cb(t);
  });
  const si = window.setInterval;
  window.setInterval = function (fn, d, ...a) { S.intervals.push(d | 0); return si.call(this, fn, d, ...a); };
  const P = window.CanvasRenderingContext2D && CanvasRenderingContext2D.prototype;
  if (P) {
    for (const m of ['fillRect', 'strokeRect', 'rect', 'roundRect', 'arc', 'ellipse', 'fillText', 'strokeText', 'drawImage', 'putImageData',
      'translate', 'setTransform', 'rotate', 'scale', 'createLinearGradient', 'createRadialGradient']) {
      const o = P[m]; if (typeof o !== 'function') continue;
      P[m] = function (...a) {
        S.draw[m] = (S.draw[m] || 0) + 1;
        if (m === 'fillRect' || m === 'rect') { if (Math.abs(a[2]) <= 6 && Math.abs(a[3]) <= 6) S.cur++; }
        if (m === 'arc' && Math.abs(a[2]) <= 3) S.cur++;
        if ((m === 'fillText' || m === 'strokeText') && /\p{Extended_Pictographic}/u.test(String(a[0]))) S.emojiText++;
        return o.apply(this, a);
      };
    }
    for (const [prop, key, test] of [['globalAlpha', 'alpha', v => v < 0.99], ['shadowBlur', 'shadows', v => v > 0]]) {
      const d = Object.getOwnPropertyDescriptor(P, prop);
      if (d && d.set) Object.defineProperty(P, prop, { configurable: true, get() { return d.get.call(this); }, set(v) { if (test(v)) S[key]++; d.set.call(this, v); } });
    }
  }
  for (const G of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) if (G) {
    for (const m of ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced']) {
      const o = G.prototype[m]; if (o) G.prototype[m] = function (...a) { S.draw.webgl = (S.draw.webgl || 0) + 1; return o.apply(this, a); };
    }
  }
  for (const N of [window.AudioBufferSourceNode, window.OscillatorNode]) if (N) {
    const o = N.prototype.start; N.prototype.start = function (...a) { S.audio++; return o.apply(this, a); };
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  if (AC) { const W = function (...a) { S.audio++; return new AC(...a); }; W.prototype = AC.prototype; window.AudioContext = W; window.webkitAudioContext = W; }
  const mp = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { if (!(this instanceof HTMLVideoElement)) { S.audio++; if (S.snd) { S.snd.mediaPlays = (S.snd.mediaPlays || 0) + 1; const u = this.currentSrc || this.src; if (u && S.snd.media.length < 50) S.snd.media.push(u); } } const r = mp.apply(this, arguments); if (r && r.catch) r.catch(() => {}); return r; };
  // ---- Web Audio: how the game's sound is BUILT (synth vs samples, effects, variation) + a recording of the mix
  S.snd = { osc: [], buffers: 0, bufferRates: [], filters: 0, convolvers: 0, compressors: 0, shapers: 0, ramps: 0, media: [] };
  S.rec = { chunks: [], len: 0, sr: 44100, on: false };
  const BAC = window.BaseAudioContext ? BaseAudioContext.prototype : (window.AudioContext && AudioContext.prototype);
  if (BAC) {
    const wrapCount = (m, key) => { const o = BAC[m]; if (o) BAC[m] = function (...a) { S.snd[key]++; return o.apply(this, a); }; };
    wrapCount('createBiquadFilter', 'filters'); wrapCount('createConvolver', 'convolvers');
    wrapCount('createDynamicsCompressor', 'compressors'); wrapCount('createWaveShaper', 'shapers');
    const co = BAC.createOscillator;
    if (co) BAC.createOscillator = function (...a) {
      const o = co.apply(this, a), st = o.start;
      o.start = function (...b) { if (S.snd.osc.length < 300) S.snd.osc.push({ type: o.type, hz: Math.round(o.frequency.value), t: Math.round(performance.now()) }); return st.apply(this, b); };
      return o;
    };
    const cb = BAC.createBufferSource;
    if (cb) BAC.createBufferSource = function (...a) {
      const s = cb.apply(this, a), st = s.start;
      s.start = function (...b) { S.snd.buffers++; if (S.snd.bufferRates.length < 300) S.snd.bufferRates.push(+s.playbackRate.value.toFixed(3)); return st.apply(this, b); };
      return s;
    };
  }
  if (window.AudioParam) for (const m of ['linearRampToValueAtTime', 'exponentialRampToValueAtTime', 'setTargetAtTime', 'setValueCurveAtTime']) {
    const o = AudioParam.prototype[m]; if (o) AudioParam.prototype[m] = function (...a) { S.snd.ramps++; return o.apply(this, a); };
  }
  // record whatever reaches the speakers (first context, up to 20 s, mono)
  if (window.AudioNode) {
    const conn = AudioNode.prototype.connect;
    AudioNode.prototype.connect = function (dest, ...a) {
      const r = conn.call(this, dest, ...a);
      try {
        const ctx = this.context;
        if (dest && ctx && dest === ctx.destination && this !== ctx.__slTap) {
          if (!ctx.__slTap && ctx.createScriptProcessor) {
            const sp = ctx.createScriptProcessor(4096, 1, 1); ctx.__slTap = sp; S.rec.sr = ctx.sampleRate;
            sp.onaudioprocess = e => { if (!S.rec.on || S.rec.len > S.rec.sr * 20) return; const c = new Float32Array(e.inputBuffer.getChannelData(0)); S.rec.chunks.push(c); S.rec.len += c.length; };
            conn.call(sp, ctx.destination);
          }
          if (ctx.__slTap) conn.call(this, ctx.__slTap);
        }
      } catch {}
      return r;
    };
  }
  for (const k of ['alert', 'confirm', 'prompt']) {
    window[k] = msg => { const d = { type: k, message: String(msg ?? '').slice(0, 140) }; S.dialogs.push(d); try { window.__slReport && window.__slReport(d); } catch {} return k === 'confirm' ? true : k === 'prompt' ? '' : undefined; };
  }
};

// ---------------------------------------------------------------- DOM measurement (runs in page)
const MEASURE = () => {
  const vw = innerWidth, vh = innerHeight;
  const tx = e => String(e.innerText ?? e.textContent ?? '');
  const sel = el => { const out = []; let e = el; for (let i = 0; e && e.nodeType === 1 && i < 3; i++, e = e.parentElement) {
    let s = e.tagName.toLowerCase(); if (e.id) { s += '#' + e.id; out.unshift(s); break; }
    const c = (typeof e.className === 'string' ? e.className : '').trim().split(/\s+/).filter(Boolean).slice(0, 2); if (c.length) s += '.' + c.join('.');
    out.unshift(s); } return out.join(' > '); };
  const parse = c => { const m = /rgba?\(([^)]+)\)/.exec(c || ''); if (!m) return null; const p = m[1].split(/[\s,/]+/).filter(Boolean).map(parseFloat);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const blend = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hsl = ({ r, g, b }) => { r /= 255; g /= 255; b /= 255; const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2; let h = 0, s = 0;
    if (mx !== mn) { const d = mx - mn; s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; } return { h, s, l }; };
  const vis = el => { const r = el.getBoundingClientRect(); if (r.width < 1 || r.height < 1) return false; const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const bgCache = new Map();
  const bgOf = el => { const chain = []; let e = el; let res = null;
    while (e && e.nodeType === 1) { if (bgCache.has(e)) { res = bgCache.get(e); break; } chain.push(e); const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') { res = { gradient: true }; break; }
      const c = parse(s.backgroundColor); if (c && c.a >= 0.6) { res = { color: c }; break; } e = e.parentElement; }
    if (!res) res = { color: { r: 255, g: 255, b: 255, a: 1 } }; chain.forEach(x => bgCache.set(x, res)); return res; };

  // ---- text: fonts, contrast, alignment, sizes
  const fam = {}, sizes = {}; let chars = 0, center = 0, alignBase = 0, lowChars = 0, tiny = 0, emoji = 0; const low = [];
  const headFam = {};
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const texts = [];
  while (tw.nextNode()) {
    const t = tw.currentNode, txt = t.textContent.replace(/\s+/g, ' ').trim(); if (!txt) continue;
    const el = t.parentElement; if (!el || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE)$/.test(el.tagName) || !vis(el)) continue;
    const s = getComputedStyle(el), n = txt.length, fsz = parseFloat(s.fontSize);
    chars += n; texts.push(txt);
    const f = s.fontFamily.split(',')[0].trim().replace(/["']/g, '').toLowerCase(); fam[f] = (fam[f] || 0) + n;
    if (el.closest('h1,h2,h3')) headFam[f] = (headFam[f] || 0) + n;
    sizes[Math.round(fsz)] = (sizes[Math.round(fsz)] || 0) + n;
    if (fsz < 12) tiny += n;
    if (n >= 40) { alignBase += n; if (s.textAlign === 'center') center += n; }
    if (!/mono|courier|consolas|menlo/i.test(s.fontFamily)) emoji += (txt.match(/\p{Extended_Pictographic}/gu) || []).filter(e => !'★☆✓✔©®™'.includes(e) && !(e.codePointAt(0) >= 0x2190 && e.codePointAt(0) <= 0x21FF)).length;
    let bg = bgOf(el);
    const col = parse(s.color);
    {
      const r0 = el.getBoundingClientRect(), cx = r0.left + r0.width / 2, cy = r0.top + r0.height / 2;
      if (cx >= 0 && cy >= 0 && cx < innerWidth && cy < innerHeight) {
        for (const x of document.elementsFromPoint(cx, cy)) {
          if (x === el || el.contains(x)) continue;
          const xs = getComputedStyle(x);
          if (xs.backgroundImage && xs.backgroundImage !== 'none') { bg = { gradient: true }; break; }
          const c = parse(xs.backgroundColor); if (c && c.a >= 0.6) { bg = { color: c }; break; }
        }
      }
    }
    const rr = el.getBoundingClientRect();
    const overMedia = rr.top < innerHeight * 3 && document.elementsFromPoint(Math.min(innerWidth - 1, Math.max(0, rr.left + rr.width / 2)), Math.min(innerHeight - 1, Math.max(0, rr.top + rr.height / 2)))
      .some(x => x !== el && !x.contains(el) && (/^(IMG|VIDEO|CANVAS|PICTURE|svg)$/i.test(x.tagName) || (getComputedStyle(x).backgroundImage || 'none') !== 'none'));
    if (bg.color && col && !overMedia) {
      const cr = contrast(blend(col, bg.color), bg.color), large = fsz >= 24 || (fsz >= 18.6 && +s.fontWeight >= 700);
      if (col.a >= 0.1 && cr >= 1.15 && cr < (large ? 3 : 4.5)) { lowChars += n; if (low.length < 8) low.push({ text: txt.slice(0, 48), ratio: +cr.toFixed(2), sel: sel(el) }); }
    }
  }

  // ---- boxes: gradients, glass, blobs, radius, shadows
  const grads = []; const eases = new Set(), grids = new Set(); let featureSet = 0;
  let gradText = 0, gradTextMono = 0, glass = 0, rTotal = 0, rBig = 0, shBig = 0, shGlow = 0; const blobs = [];
  const all = [...document.body.querySelectorAll('*')].slice(0, 6000);
  for (const el of all) {
    if (!vis(el)) continue; const s = getComputedStyle(el), r = el.getBoundingClientRect();
    if (s.backgroundImage.includes('gradient')) {
      const cols = [...s.backgroundImage.matchAll(/rgba?\([^)]+\)/g)].map(m => parse(m[0])).filter(c => c && c.a > 0.15);
      const hs = cols.map(hsl).filter(h => h.s > 0.35 && h.l > 0.18 && h.l < 0.85 && h.h >= 200 && h.h <= 340);
      const hues = hs.map(h => h.h);
      if (hs.length >= 2 && hues.some(h => h >= 250 && h <= 335) && Math.max(...hues) - Math.min(...hues) >= 18)
        grads.push({ sel: sel(el), area: +((r.width * r.height) / (vw * vh)).toFixed(3), hues: hues.map(Math.round) });
      if (s.webkitBackgroundClip === 'text' || s.backgroundClip === 'text') {
        const sat = cols.map(hsl).filter(h => h.s > 0.3 && h.l > 0.15 && h.l < 0.9).map(h => h.h);
        if (sat.length >= 2 && Math.max(...sat) - Math.min(...sat) >= 30) gradText++; else gradTextMono++;
      }
    }
    if (s.backdropFilter && s.backdropFilter.includes('blur')) glass++;
    const fb = /blur\(([\d.]+)px\)/.exec(s.filter || ''); if (fb && +fb[1] >= 30 && r.width >= 100) blobs.push({ sel: sel(el), blur: +fb[1] });
    const hasBg = (parse(s.backgroundColor)?.a || 0) > 0.05 || s.backgroundImage !== 'none' || parseFloat(s.borderTopWidth) > 0;
    if (hasBg && r.width >= 40 && r.height >= 24) { rTotal++; const br = parseFloat(s.borderTopLeftRadius) || 0; if (br >= 12 && br < Math.min(r.width, r.height) / 2 - 1) rBig++; }
    // craft evidence: bespoke motion curves, varied grid systems, OpenType/variable-font detailing
    for (const tf of [s.transitionTimingFunction, s.animationTimingFunction]) {
      if (tf && tf.includes('cubic-bezier') && !/cubic-bezier\((0\.4, 0, 0\.2, 1|0\.25, 0\.1, 0\.25, 1|0, 0, 0\.2, 1|0\.4, 0, 1, 1|0\.42, 0, 0\.58, 1)\)/.test(tf)) eases.add(tf.slice(0, 60));
    }
    if (s.display.includes('grid') && el.children.length >= 2 && s.gridTemplateColumns !== 'none') grids.add(s.gridTemplateColumns.replace(/[\d.]+px/g, m => Math.round(parseFloat(m) / 40) * 40 + 'px'));
    if ((s.fontFeatureSettings && s.fontFeatureSettings !== 'normal') || (s.fontVariationSettings && s.fontVariationSettings !== 'normal')) featureSet++;
    if (s.boxShadow && s.boxShadow !== 'none') {
      for (const part of s.boxShadow.split(/,(?![^(]*\))/)) {
        const nums = (part.replace(/rgba?\([^)]*\)/, '').match(/-?[\d.]+px/g) || []).map(parseFloat);
        const [x = 0, y = 0, blur = 0] = nums; const c = parse(part);
        if (blur >= 20) shBig++;
        if (x === 0 && y === 0 && blur >= 15 && c && hsl(c).s > 0.4) shGlow++;
      }
    }
  }
  // ---- uniform card rows
  const rows = [];
  for (const p of all) {
    if (p.children.length < 3 || !vis(p)) continue;
    const kids = [...p.children].filter(k => vis(k)).map(k => ({ k, r: k.getBoundingClientRect() })).filter(o => o.r.width >= 140 && o.r.height >= 90 && tx(o.k).trim().length > 10);
    const byTop = {}; for (const o of kids) { const key = Math.round(o.r.top / 6); (byTop[key] = byTop[key] || []).push(o); }
    for (const g of Object.values(byTop)) {
      if (g.length >= 3 && g.every(o => Math.abs(o.r.width - g[0].r.width) <= 3 && Math.abs(o.r.height - g[0].r.height) <= 8)) { rows.push({ sel: sel(p), n: g.length }); break; }
    }
  }
  // ---- sections, images, headings, buttons
  const sections = [...document.querySelectorAll('section, main > *, body > header, body > footer')].filter(e => vis(e) && e.getBoundingClientRect().height >= 200).length;
  const imgs = [...document.images].filter(vis).slice(0, 80).map(i => ({ src: (i.currentSrc || i.src).slice(0, 200), nw: i.naturalWidth, nh: i.naturalHeight,
    alt: i.getAttribute('alt'), broken: i.complete && i.naturalWidth === 0 }));
  const headings = [...document.querySelectorAll('h1,h2,h3')].filter(vis).map(h => [+h.tagName[1], tx(h).trim().slice(0, 160)]);
  const buttons = [...document.querySelectorAll('a,button,[role=button]')].filter(vis).map(b => tx(b).trim().slice(0, 60)).filter(Boolean).slice(0, 120);
  const canv = [...document.querySelectorAll('canvas')].filter(vis).map(c => { const r = c.getBoundingClientRect(); return r.width * r.height / (vw * vh); });
  const famSorted = Object.entries(fam).sort((a, b) => b[1] - a[1]);
  return {
    viewport: [vw, vh], chars, words: texts.join(' ').split(/\s+/).filter(Boolean).length,
    fonts: famSorted.slice(0, 6).map(([f, n]) => [f, +(n / Math.max(1, chars)).toFixed(3)]),
    headingFonts: Object.keys(headFam), fontSizes: Object.keys(sizes).length,
    contrast: { lowShare: +(lowChars / Math.max(1, chars)).toFixed(3), samples: low },
    centerShare: alignBase ? +(center / alignBase).toFixed(3) : 0, longTextChars: alignBase,
    tinyTextShare: +(tiny / Math.max(1, chars)).toFixed(3), emoji,
    gradients: grads.slice(0, 12), gradientCount: grads.length, gradientText: gradText, gradientTextMono: gradTextMono, glass, blobs: blobs.slice(0, 8),
    radius: { total: rTotal, big: rBig }, shadows: { big: shBig, glow: shGlow },
    cardRows: rows.slice(0, 10), sections, imgs, headings, buttons,
    canvasCover: canv.length ? +Math.max(...canv).toFixed(3) : 0,
    docHeight: document.documentElement.scrollHeight,
    craft: (() => {
      const DEF = ['inter', 'poppins', 'roboto', 'open sans', 'montserrat', 'arial', 'helvetica', 'system-ui', 'dm sans', 'plus jakarta sans', 'outfit', 'manrope', 'geist', 'lato', 'nunito'];
      const loaded = [...new Set([...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/["']/g, '').toLowerCase()))];
      const svgs = [...document.querySelectorAll('svg')].filter(vis);
      const illus = svgs.filter(v => v.innerHTML.length > 4000).length;
      const bigImgs = [...document.images].filter(i => vis(i) && i.naturalWidth >= 800).length;
      const videos = [...document.querySelectorAll('video')].filter(vis).length;
      return { customFonts: loaded.filter(f => !DEF.includes(f)).slice(0, 8), bespokeEasings: eases.size, gridSystems: grids.size,
               typeFeatures: featureSet, svgIllustrations: illus, bigImages: bigImgs, videos };
    })(),
  };
};

// on-screen text as a person reads it: size, caps, tracking, and whether it sits on a button
const TEXTS = () => {
  const out = [], seen = new Set();
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight * 3 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode() && out.length < 400) {
    const el = tw.currentNode.parentElement; const t = tw.currentNode.textContent.replace(/\s+/g, ' ').trim();
    if (!el || !t || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName) || !vis(el)) continue;
    // group by what a reader perceives as one unit: a whole button, then a whole paragraph/heading
    const blk = el.closest('button,a,[role=button]') || el.closest('label,p,li,h1,h2,h3,h4,dt,dd,figcaption') || el;
    const full = (blk.innerText || t).replace(/\s+/g, ' ').trim().slice(0, 120);
    if (seen.has(full)) continue; seen.add(full);
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    out.push({ t: full, fs: Math.round(parseFloat(s.fontSize)), up: s.textTransform === 'uppercase' || (/[A-Za-z]{2}/.test(t) && t === t.toUpperCase()),
      ls: +(parseFloat(s.letterSpacing) || 0).toFixed(1), btn: !!el.closest('button,[role=button]'), h: !!el.closest('h1,h2,h3'),
      y: Math.round(r.top) });
  }
  return out;
};

const MOBILE = () => {
  const vw = innerWidth;
  const sel = el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : (typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/)[0] : ''));
  const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const overflow = document.documentElement.scrollWidth > vw + 2;
  const offenders = overflow ? [...document.body.querySelectorAll('*')].filter(e => vis(e) && e.getBoundingClientRect().right > vw + 2)
    .filter(e => !e.parentElement || e.parentElement.getBoundingClientRect().right <= vw + 2).slice(0, 6).map(e => ({ sel: sel(e), right: Math.round(e.getBoundingClientRect().right) })) : [];
  const targets = [...document.querySelectorAll('a,button,input,select,textarea,[role=button]')].filter(vis);
  const small = targets.filter(e => { const r = e.getBoundingClientRect(); return Math.min(r.width, r.height) < 24 && !(e.tagName === 'A' && e.closest('p,li')); });
  let tiny = 0, chars = 0; const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (tw.nextNode()) { const t = tw.currentNode.textContent.trim(); const el = tw.currentNode.parentElement; if (!t || !el || !vis(el)) continue;
    chars += t.length; if (parseFloat(getComputedStyle(el).fontSize) < 12) tiny += t.length; }
  const noViewport = vw > 500;
  return { noViewport, layoutWidth: vw, overflow, scrollWidth: document.documentElement.scrollWidth, offenders, targets: targets.length,
    smallTargets: small.length, smallSamples: small.slice(0, 5).map(sel), tinyTextShare: +(tiny / Math.max(1, chars)).toFixed(3) };
};

// ---------------------------------------------------------------- helpers
async function shot(page, name, opts = {}) {
  if (!OUT) return null;
  const p = path.join(OUT, name + '.png');
  try { await page.screenshot({ path: p, ...opts }); return p; } catch { return null; }
}
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

async function focusTest(page) {
  const res = { tested: 0, invisible: [] };
  try {
    await page.evaluate(() => { document.activeElement?.blur?.(); window.scrollTo(0, 0); });
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab');
      const r = await page.evaluate(() => {
        const el = document.activeElement; if (!el || el === document.body) return null;
        const pick = s => [s.outlineStyle, s.outlineWidth, s.outlineColor, s.boxShadow, s.backgroundColor, s.borderColor, s.textDecorationLine, s.color].join('|');
        const on = pick(getComputedStyle(el)); el.blur(); const off = pick(getComputedStyle(el)); el.focus({ focusVisible: true });
        return { tag: el.tagName.toLowerCase(), text: (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 40), visible: on !== off };
      });
      if (!r) continue; res.tested++; if (!r.visible) res.invisible.push(r);
    }
  } catch (e) { res.error = e.message.split('\n')[0]; }
  return res;
}

async function clickTest(ctx, url) {
  const out = { tested: 0, dead: [], alive: 0, skipped: 0, dialogs: [] };
  const page = await ctx.newPage();
  try {
    await go(page, url);
    const cands = await page.evaluate(max => {
      const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none'; };
      const els = [...document.querySelectorAll('a,button,[role=button],[onclick],input[type=submit]')].filter(vis);
      const pick = []; const seen = new Set();
      for (const [i, el] of els.entries()) {
        const href = el.getAttribute('href'); const text = (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim().slice(0, 50);
        let ext = false; if (href && /^(https?:)?\/\//.test(href)) { try { ext = new URL(href, location.href).origin !== location.origin; } catch {} }
        if (href && /^(mailto|tel):/.test(href)) continue;
        const key = text + '|' + href + '|' + !!el.closest('form'); if (seen.has(key)) continue; seen.add(key);
        pick.push({ i, text, href, ext, tag: el.tagName.toLowerCase(), inForm: !!el.closest('form'), submit: el.type === 'submit' || el.hasAttribute('download') });
      }
      return pick.slice(0, max);
    }, MAX_CLICKS);
    out.safeMode = REMOTE;
    for (const c of cands) {
      if (REMOTE && (c.inForm || c.submit || RISKY.test(c.text || '') || RISKY.test(c.href || ''))) { out.skipped++; continue; }
      if (c.ext) { out.skipped++; continue; }
      if (c.href && c.href.startsWith('#') && c.href.length > 1) {
        const exists = await page.evaluate(h => { try { return !!document.querySelector(h) || !!document.getElementsByName(h.slice(1)).length; } catch { return false; } }, c.href);
        if (exists) { out.tested++; out.alive++; continue; }
        c.missingAnchor = true;
      }
      if (c.href === '#' || /^javascript:\s*(void\(0\)|;)?\s*$/i.test(c.href || '')) {
        // a bare '#' only "works" if JS handles it — test by clicking
      }
      if (overBudget()) { out.stoppedEarly = true; break; }
      await go(page, url);
      const before = await page.evaluate(i => {
        const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none'; };
        const el = [...document.querySelectorAll('a,button,[role=button],[onclick],input[type=submit]')].filter(vis)[i]; if (!el) return null;
        el.setAttribute('data-sl-target', '1'); el.scrollIntoView({ block: 'center' });
        window.__slMut = 0; new MutationObserver(ms => { for (const m of ms) if (!(m.type === 'attributes' && m.attributeName === 'data-sl-target')) window.__slMut++; })
          .observe(document.documentElement, { subtree: true, childList: true, attributes: true, characterData: true });
        return { url: location.href, dialogs: (window.__sl?.dialogs || []).length };
      }, c.i);
      if (!before) { out.skipped++; continue; }
      let req = 0; const onReq = () => req++; page.on('request', onReq);
      let popup = false; const onPopup = () => { popup = true; }; page.on('popup', onPopup);
      let navigated = false;
      try {
        await page.click('[data-sl-target="1"]', { timeout: 2500, noWaitAfter: true });
      } catch { page.off('request', onReq); page.off('popup', onPopup); out.skipped++; continue; }
      await page.waitForTimeout(700);
      let after;
      try {
        after = await page.evaluate(() => ({ url: location.href, mut: window.__slMut ?? -1, dialogs: window.__sl?.dialogs || [] }));
      } catch { navigated = true; }
      page.off('request', onReq); page.off('popup', onPopup);
      out.tested++;
      if (navigated || !after || after.mut === -1) { out.alive++; continue; }
      const newDialogs = after.dialogs.slice(before.dialogs);
      out.dialogs.push(...newDialogs.map(d => ({ ...d, trigger: c.text })));
      const urlChanged = after.url !== before.url && !(after.url.endsWith('#') && after.url.slice(0, -1) === before.url.replace(/#$/, ''));
      const effect = urlChanged || after.mut > 0 || req > 0 || popup;
      if (effect) out.alive++;
      else out.dead.push({ ...c, reason: newDialogs.length ? 'alert만 뜨고 실제 동작 없음' : c.missingAnchor ? `존재하지 않는 앵커 ${c.href}, 클릭해도 변화 없음` : '클릭해도 화면·주소·네트워크 변화 없음' });
      if (!effect && newDialogs.length) out.alive += 0;
    }
  } catch (e) { out.error = e.message.split('\n')[0]; }
  await page.close();
  return out;
}

async function canvasInfo(page) {
  return page.evaluate(() => {
    const cs = [...document.querySelectorAll('canvas')]; if (!cs.length) return null;
    const c = cs.sort((a, b) => b.width * b.height - a.width * a.height)[0];
    const r = c.getBoundingClientRect();
    const info = { w: c.width, h: c.height, cssW: Math.round(r.width), cssH: Math.round(r.height), dpr: devicePixelRatio, kind: null, palette: null };
    let g = null; try { g = c.getContext('2d'); } catch {}
    if (!g) { info.kind = 'webgl'; return info; }
    info.kind = '2d';
    try {
      const step = Math.max(1, Math.floor(Math.sqrt((c.width * c.height) / 40000)));
      const d = g.getImageData(0, 0, c.width, c.height).data; const cnt = new Map(); let n = 0;
      for (let y = 0; y < c.height; y += step) for (let x = 0; x < c.width; x += step) {
        const i = (y * c.width + x) * 4; const k = ((d[i] >> 4) << 8) | ((d[i + 1] >> 4) << 4) | (d[i + 2] >> 4); cnt.set(k, (cnt.get(k) || 0) + 1); n++; }
      const arr = [...cnt.entries()].sort((a, b) => b[1] - a[1]); const bg = arr[0];
      const rest = n - bg[1]; let prim = 0; let distinct = 0;
      for (const [k, v] of arr.slice(1)) {
        if (v / n >= 0.001) distinct++;
        const r8 = k >> 8, g8 = (k >> 4) & 15, b8 = k & 15; const ext = [r8, g8, b8].every(q => q <= 1 || q >= 14);
        const bw = [r8, g8, b8].every(q => q <= 1) || [r8, g8, b8].every(q => q >= 14);
        if (ext && !bw) prim += v;
      }
      info.palette = { distinct, primaryShare: rest ? +(prim / rest).toFixed(3) : 0, bgShare: +(bg[1] / n).toFixed(3) };
    } catch (e) { info.palette = { error: 'tainted' }; }
    return info;
  });
}

async function canvasHash(page) {
  // canvas games: hash the canvas; DOM games (idle, text, tile puzzles): hash the viewport instead
  try {
    const el = await page.$('canvas');
    const box = el ? await el.boundingBox() : null;
    const buf = (box && box.width * box.height > 200 * 150) ? await el.screenshot({ timeout: 3000 })
      : await page.screenshot({ timeout: 3000, type: 'jpeg', quality: 40 });
    return crypto.createHash('md5').update(buf).digest('hex');
  } catch { return null; }
}

async function playGame(page, out) {
  const g = { navigations: 0, played_ms: 0 };
  const onNav = f => { if (f === page.mainFrame()) g.navigations++; };
  page.on('framenavigated', onNav);
  const h0 = await canvasHash(page); await page.waitForTimeout(900); const h1 = await canvasHash(page);
  g.animatesIdle = !!(h0 && h1 && h0 !== h1);
  g.hasCanvas = await page.evaluate(() => [...document.querySelectorAll('canvas')].some(c => { const r = c.getBoundingClientRect(); return r.width * r.height > innerWidth * innerHeight * 0.25; })).catch(() => false);
  out.screenshots.game.push(await shot(page, 'game-0-start'));
  const box = await page.evaluate(() => { const c = document.querySelector('canvas'); if (!c) return null; const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }; });
  const cx = box ? box.x : 640, cy = box ? box.y : 360;
  // Many games start from an HTML button (title → level select …). Press visible start-like buttons first.
  g.startClicks = [];
  for (let k = 0; k < 3; k++) {
    const label = await page.evaluate(() => {
      const rx = /^(▶\s*)?(play|start|start game|new game|continue|retry|tap to start|press start|level ?1|stage ?1|플레이|시작|게임 시작|시작하기|계속|다시 시작|1단계|스테이지 ?1)\b/i;
      const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 4 && r.height > 4 && s.visibility !== 'hidden' && s.display !== 'none'; };
      const el = [...document.querySelectorAll('button,[role=button],a,input[type=button]')].filter(vis)
        .find(b => rx.test(String(b.innerText ?? b.textContent ?? b.value ?? '').trim()));
      if (!el) return null; el.setAttribute('data-sl-start', '1'); return String(el.innerText ?? el.textContent ?? el.value).trim().slice(0, 30);
    }).catch(() => null);
    if (!label) break;
    try { await page.click('[data-sl-start="1"]', { timeout: 2000 }); g.startClicks.push(label); } catch { break; }
    await page.evaluate(() => document.querySelectorAll('[data-sl-start]').forEach(e => e.removeAttribute('data-sl-start'))).catch(() => {});
    await page.waitForTimeout(900);
  }
  try { await page.mouse.click(cx, cy); await page.keyboard.press('Enter'); await page.keyboard.press('Space'); } catch {}
  const R = rng(42), keys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyZ', 'KeyX', 'KeyJ', 'Enter'];
  await page.evaluate(() => { if (window.__sl) window.__sl.rec.on = true; }).catch(() => {});
  const start = Date.now(); let i = 0, mid = false;
  const hBefore = await canvasHash(page);
  while (Date.now() - start < PLAY_MS) {
    const k = keys[Math.floor(R() * keys.length)];
    try { await page.keyboard.down(k); await page.waitForTimeout(100 + R() * 260); await page.keyboard.up(k);
      if (i % 4 === 0 && box) await page.mouse.click(cx + (R() - 0.5) * box.w * 0.6, cy + (R() - 0.5) * box.h * 0.6); } catch {}
    if (!mid && Date.now() - start > PLAY_MS * 0.45) { out.screenshots.game.push(await shot(page, 'game-1-mid')); mid = true; }
    i++;
  }
  g.played_ms = Date.now() - start;
  const hAfter = await canvasHash(page);
  g.changedDuringPlay = !!(hBefore && hAfter && hBefore !== hAfter);
  out.screenshots.game.push(await shot(page, 'game-2-end'));
  page.off('framenavigated', onNav);
  const s = await page.evaluate(() => window.__sl ? { raf: window.__sl.raf, intervals: window.__sl.intervals, audio: window.__sl.audio, dialogs: window.__sl.dialogs,
    draw: window.__sl.draw, emojiText: window.__sl.emojiText, alpha: window.__sl.alpha, shadows: window.__sl.shadows, small: window.__sl.small } : null).catch(() => null);
  if (s) {
    const iv = []; for (let k = 1; k < s.raf.length; k++) iv.push(s.raf[k] - s.raf[k - 1]);
    const sorted = [...iv].sort((a, b) => a - b); const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    g.rafFrames = s.raf.length; g.medianFrameMs = +med.toFixed(2); g.fps = med ? Math.round(1000 / med) : 0;
    g.longFrameShare = iv.length ? +(iv.filter(x => x > 34).length / iv.length).toFixed(3) : 0;
    g.intervals = s.intervals.slice(0, 10); g.audioCalls = s.audio; g.dialogs = s.dialogs; g.draw = s.draw; g.emojiText = s.emojiText;
    const frames = Math.max(1, s.raf.length);
    const tr = (s.draw.translate || 0) + (s.draw.rotate || 0) + (s.draw.scale || 0) + Math.max(0, (s.draw.setTransform || 0) - 2);
    g.juice = {
      alphaFx: s.alpha >= 10, transforms: tr >= 10, glow: s.shadows >= 10,
      gradients: ((s.draw.createLinearGradient || 0) + (s.draw.createRadialGradient || 0)) > 0,
      particles: s.small.filter(v => v >= 12).length > 5,
    };
  }
  g.canvas = await canvasInfo(page).catch(() => null);
  g.uiTexts = await page.evaluate(TEXTS).catch(() => []);
  g.sound = await page.evaluate(() => {
    const S = window.__sl; if (!S) return null;
    const snd = S.snd, osc = snd.osc;
    const types = {}; osc.forEach(o => { types[o.type] = (types[o.type] || 0) + 1; });
    const voices = [...new Set(osc.map(o => o.type + ':' + o.hz))];
    const rates = [...new Set(snd.bufferRates)];
    const media = [...new Set([...document.querySelectorAll('audio')].map(a => a.currentSrc || a.src).filter(Boolean).concat(snd.media || []))];
    let mix = null;
    if (S.rec.len > S.rec.sr * 0.5) {
      const x = new Float32Array(S.rec.len); let o = 0; for (const c of S.rec.chunks) { x.set(c, o); o += c.length; }
      mix = window.__slLib ? window.__slLib.audioFeatures(x, S.rec.sr) : null;
    }
    return { oscillatorPlays: osc.length, oscillatorTypes: types, distinctSynthVoices: voices.slice(0, 20), samplePlays: snd.buffers,
      sampleRateVariety: rates.length, filters: snd.filters, reverbs: snd.convolvers, compressors: snd.compressors, distortion: snd.shapers,
      envelopeRamps: snd.ramps, mediaFiles: media.slice(0, 10), mediaPlays: snd.mediaPlays || 0, mix };
  }).catch(() => null);
  return g;
}

// ---------------------------------------------------------------- main
let PARTIAL = null;
setTimeout(() => {
  if (PARTIAL && PARTIAL.desktop) { PARTIAL.ok = true; PARTIAL.partial = true; PARTIAL.notes.push('시간 예산 초과: 측정된 부분까지만 반환'); emit(PARTIAL); }
  else emit({ ok: false, error: '렌더 프로브 시간 예산 초과', elapsed_ms: Date.now() - t0 });
  process.exit(0);
}, BUDGET_MS + 60000).unref();

async function main() {
  const out = { ok: false, version: '0.2.0', screenshots: { game: [] }, notes: [] };
  PARTIAL = out;
  let server = null, url = args.url;
  if (!url) {
    if (!args.root) throw new Error('--url 또는 --root 필요');
    server = await serve(args.root);
    url = `http://127.0.0.1:${server.address().port}/${(args.entry || 'index.html').split(path.sep).join('/')}`;
  }
  if (OUT) fs.mkdirSync(OUT, { recursive: true });
  const { browser, name } = await launch();
  out.browser = name; out.url = url;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const allDialogs = [];
  await ctx.exposeBinding('__slReport', (_src, d) => { if (allDialogs.length < 30) allDialogs.push(d); });
  await ctx.addInitScript(INSTRUMENT);
  await ctx.addInitScript({ content: LIB });
  const page = await ctx.newPage();
  const consoleErrors = [], failed = [];
  page.on('console', m => { if (m.type() === 'error' && consoleErrors.length < 12) consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', e => { if (consoleErrors.length < 12) consoleErrors.push(('pageerror: ' + e.message).slice(0, 200)); });
  page.on('requestfailed', r => { if (r.failure()?.errorText === 'net::ERR_ABORTED') return; if (failed.length < 12) failed.push({ url: r.url().slice(0, 160), error: r.failure()?.errorText }); });
  page.on('response', r => { if (r.status() >= 400 && failed.length < 12) failed.push({ url: r.url().slice(0, 160), status: r.status() }); });
  // keep the raster art the page actually loads (sprites, card art, backgrounds) for provenance + pixel analysis
  const assetJobs = [], assets = [];
  page.on('response', r => {
    if (!OUT || assetJobs.length >= 80) return;
    const ct = (r.headers()['content-type'] || '').toLowerCase();
    if (!/image\/(png|jpe?g|webp)/.test(ct) || r.status() >= 300) return;
    // only the site's own art — ads and third-party embeds are not the work being judged
    let ah = ''; try { ah = new URL(r.url()).hostname; } catch { return; }
    const ph = (() => { try { return new URL(url).hostname; } catch { return ''; } })();
    const base = ph.split('.').slice(-2).join('.'), brand = (ph.replace(/^www\./, '').split('.')[0] || '').slice(0, 12);
    if (!(ah === ph || ah.endsWith('.' + base) || (brand.length >= 4 && ah.includes(brand)))) return;
    assetJobs.push(r.body().then(b => {
      if (b.length < 15000 || assets.length >= 40) return;
      const ext = ct.includes('png') ? 'png' : ct.includes('webp') ? 'webp' : 'jpg';
      const base = (decodeURIComponent(r.url().split('?')[0].split('/').pop() || 'img')).replace(/[^\w.-]/g, '_').replace(/\.(png|jpe?g|webp)$/i, '').slice(0, 60);
      const fp = path.join(OUT, 'assets', `a${String(assets.length).padStart(2, '0')}-${base}.${ext}`);
      fs.mkdirSync(path.dirname(fp), { recursive: true }); fs.writeFileSync(fp, b);
      assets.push({ file: fp, url: r.url().slice(0, 200), bytes: b.length });
    }).catch(() => {}));
  });
  await go(page, url, true);
  await page.waitForTimeout(900);
  out.desktop = await safeEval(page, MEASURE);
  out.desktop.uiTexts = await page.evaluate(TEXTS).catch(() => []);
  out.unbuilt = out.desktop.chars < 20 && await page.evaluate(() => [...document.querySelectorAll('script[type=module][src]')].some(s => /\.(jsx|tsx|ts|vue|svelte)(\?|$)/.test(s.getAttribute('src'))));
  if (out.unbuilt) out.notes.push('빌드되지 않은 소스(JSX/TS 모듈)가 그대로 서빙되어 화면이 비어 있습니다. `npm run dev` 후 그 URL로 검사하세요.');
  const isGame = KIND === 'game' || (KIND === 'auto' && out.desktop.canvasCover >= 0.35 && out.desktop.words < 800 && (out.desktop.buttons || []).length < 25
    && !(out.desktop.docHeight > out.desktop.viewport[1] * 1.6 && (out.desktop.headings || []).length >= 4));  // long, sectioned pages are websites
  out.kindHint = isGame ? 'game' : 'web';
  out.screenshots.desktop = await shot(page, 'desktop');
  out.html = (await page.content()).slice(0, 1_500_000);
  if (!isGame) {
    // scroll through once so lazy-loaded sections and scroll-in animations render before the full-page capture
    await page.evaluate(async () => { for (let y = 0; y < Math.min(document.documentElement.scrollHeight, 9000); y += innerHeight * 0.8) { scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); } scrollTo(0, 0); }).catch(() => {});
    await page.waitForTimeout(600);
    const fullH = Math.min(out.desktop.docHeight, 9000);
    out.screenshots.desktopFull = await shot(page, 'desktop-full', { fullPage: fullH <= 9000, clip: out.desktop.docHeight > 9000 ? { x: 0, y: 0, width: 1440, height: 9000 } : undefined });
    out.focus = await focusTest(page);
  }
  if (isGame) out.game = await playGame(page, out);
  out.dialogs = allDialogs.slice();
  out.console = { errors: consoleErrors, failed };
  if (!isGame && !overBudget()) {
    const n0 = allDialogs.length;
    out.clicks = await clickTest(ctx, url);
    out.clickDialogs = allDialogs.slice(n0);
  }
  // mobile pass
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await mctx.addInitScript(INSTRUMENT);
  const mp = await mctx.newPage();
  await go(mp, url, true);
  await mp.waitForTimeout(600);
  out.mobile = await mp.evaluate(MOBILE);
  out.screenshots.mobile = await shot(mp, 'mobile');
  await Promise.race([Promise.all(assetJobs), new Promise(r => setTimeout(r, 4000))]);
  out.assets = assets;
  await mctx.close(); await ctx.close(); await browser.close();
  if (server) server.close();
  out.screenshots.game = out.screenshots.game.filter(Boolean);
  out.ok = true; out.elapsed_ms = Date.now() - t0;
  return out;
}

try {
  emit(await main());
} catch (e) {
  emit({ ok: false, error: (e && e.message ? e.message : String(e)).split('\n')[0], elapsed_ms: Date.now() - t0 });
}
process.exit(0);
