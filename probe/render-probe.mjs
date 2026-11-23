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
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { isLocal, launchBrowser, serveDirs, guardContext, inputPolicy } from './safety.mjs';

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : 'true']);
    return acc;
  }, [])
);
const KIND = args.kind || 'auto';
const OUT = args.out || null;
const MAX_CLICKS = +(args.clicks || 12);
const PLAY_MS = +(args.play || 15000);
// On third-party sites never submit forms, buy, sign up, log in, download or accept consent (see safety.mjs).
const REMOTE = !!args.url && !isLocal(args.url);
// on a third-party page these generic labels are usually consent or confirmation, not navigation
const AMBIGUOUS = /^(ok|okay|yes|confirm|continue|got it|i understand|확인|네|예|계속|계속하기)$/i;
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
// A page that reloads itself (game over → location.reload) destroys whatever is being read. Retry, and from the
// second attempt on hold its navigations so there is a stable document to read.
const MID_NAV = /context was destroyed|navigat|Cannot find context|Unable to retrieve content|document\.body|reading '(querySelectorAll|innerText)'|parameter 1 is not of type 'Node'/i;
let GUARD = null;
async function stable(page, fn) {
  for (let i = 0; ; i++) {
    const attempt = async () => {
      if (i) {
        await page.waitForTimeout(250);
        await page.waitForLoadState('domcontentloaded', { timeout: 5000 }).catch(() => {});
      }
      return await fn();
    };
    try { return i && GUARD ? await GUARD.holdNavigation(attempt) : await attempt(); }
    catch (e) { if (i >= 5 || !MID_NAV.test(e.message)) throw e; }
  }
}
const safeEval = (page, fn, arg) => stable(page, () => page.evaluate(fn, arg));

// process.exit() drops what is still queued on a pipe (asynchronous on macOS/Linux), and this JSON can exceed 1 MB
let EMITTED = null;
function emit(obj) {
  EMITTED ??= new Promise(done => process.stdout.write(JSON.stringify(obj), () => done()));
  return EMITTED;
}

let chromium;
try {
  ({ chromium } = await import('playwright-core'));
} catch {
  try { ({ chromium } = await import('playwright')); } catch {
    await emit({ ok: false, error: 'playwright-core 미설치: SlopLens 폴더에서 `npm install` 을 실행하세요.' });
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
  return serveDirs(rel => ({ root, rel }), MIME);
}

async function launch() {
  return launchBrowser(chromium, ['--autoplay-policy=no-user-gesture-required']);
}

// ---------------------------------------------------------------- in-page instrumentation
const INSTRUMENT = () => {
  const tick = window.setInterval.bind(window);  // before it is wrapped below
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
    const o = N.prototype.start; N.prototype.start = function (...a) { S.audio++; S.flush?.(); return o.apply(this, a); };
  }
  const AC = window.AudioContext || window.webkitAudioContext;
  if (AC) { const W = function (...a) { return new AC(...a); /* creating a context is not a sound */ }; W.prototype = AC.prototype; window.AudioContext = W; window.webkitAudioContext = W; }
  const mp = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function () { if (!(this instanceof HTMLVideoElement)) { S.audio++; S.flush?.(); if (S.snd) { S.snd.mediaPlays = (S.snd.mediaPlays || 0) + 1; const u = this.currentSrc || this.src; if (u && S.snd.media.length < 50) S.snd.media.push(u); } } const r = mp.apply(this, arguments); if (r && r.catch) r.catch(() => {}); return r; };
  // ---- Web Audio: how the game's sound is BUILT (synth vs samples, effects, variation) + a recording of the mix
  S.snd = { osc: [], buffers: 0, bufferRates: [], bufferKinds: new Set(), filters: 0, convolvers: 0, compressors: 0, shapers: 0, ramps: 0, media: [] };
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
      s.start = function (...b) { S.snd.buffers++; if (S.snd.bufferRates.length < 300) S.snd.bufferRates.push(+s.playbackRate.value.toFixed(3));
        const bf = s.buffer; if (bf && S.snd.bufferKinds.size < 200) S.snd.bufferKinds.add(bf.length + ':' + bf.numberOfChannels + ':' + bf.sampleRate);
        return st.apply(this, b); };
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
  // ---- a game-over reload wipes this document, so the probe keeps the latest summary of each one
  const doc = Math.random().toString(36).slice(2);
  let frames = 0, last = '';
  const flush = () => {
    if (window !== window.top || !window.__slFlush) return;
    const n = S.snd, rec = { doc, draw: S.draw, emojiText: S.emojiText, alpha: S.alpha, shadows: S.shadows, audio: S.audio, frames: S.raf.length,
      sound: { osc: n.osc.map(o => [o.type, o.hz]), buffers: n.buffers, rates: [...new Set(n.bufferRates)], kinds: [...n.bufferKinds],
        filters: n.filters, convolvers: n.convolvers, compressors: n.compressors, shapers: n.shapers, ramps: n.ramps, media: n.media, mediaPlays: n.mediaPlays || 0 } };
    const sig = JSON.stringify(rec);
    if (sig === last) return;
    last = sig;
    try { Promise.resolve(window.__slFlush(rec)).catch(() => {}); } catch {}
  };
  S.flush = () => { if (!frames) { frames = 1; queueMicrotask(() => { frames = 0; flush(); }); } };
  if (window === window.top) { tick(flush, 500); addEventListener('pagehide', flush); }
  // answering "yes" for someone is only acceptable on the user's own local build
  const localPage = /^(localhost|127\.0\.0\.1|\[::1\]|(.+\.)?localhost)$/i.test(location.hostname);
  for (const k of ['alert', 'confirm', 'prompt']) {
    window[k] = msg => { const d = { type: k, message: String(msg ?? '').slice(0, 140) }; S.dialogs.push(d); try { window.__slReport && window.__slReport(d); } catch {} return k === 'confirm' ? localPage : k === 'prompt' ? (localPage ? '' : null) : undefined; };
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
  try { await page.screenshot({ path: p, timeout: 15000, ...opts }); return p; } catch { return null; }
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
      if ((REMOTE || !isLocal(page.url())) && (c.inForm || c.submit || AMBIGUOUS.test(c.text || '') || RISKY.test(c.text || '') || RISKY.test(c.href || ''))) { out.skipped++; continue; }
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
  // closing a page mid-navigation can hang forever: never let it block the remaining measurements
  await within(page.close(), 5000);
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

// Calls into a page that is reloading can hang (page.evaluate has no timeout of its own): never let one eat the play time.
function within(promise, ms, fallback = null) {
  let timer;
  return Promise.race([promise.catch(() => fallback), new Promise(done => { timer = setTimeout(() => done(fallback), ms); })])
    .finally(() => clearTimeout(timer));
}

async function canvasHash(page) {
  // canvas games: hash the canvas area; DOM games (idle, text, tile puzzles): hash the viewport instead.
  // Not element.screenshot(): after a reload it waits for the detached canvas until it times out.
  const area = await within(page.evaluate(() => {
    const c = document.querySelector('canvas');
    if (!c) return { clip: null };
    const r = c.getBoundingClientRect();
    const x = Math.max(0, r.left), y = Math.max(0, r.top), width = Math.min(innerWidth, r.right) - x, height = Math.min(innerHeight, r.bottom) - y;
    return { clip: width > 0 && height > 0 && width * height > 200 * 150 ? { x, y, width, height } : null };
  }), 1500);
  if (!area) return null;
  const buf = await within(page.screenshot(area.clip ? { clip: area.clip, timeout: 2000 } : { timeout: 2000, type: 'jpeg', quality: 40 }), 2500);
  return buf ? crypto.createHash('md5').update(buf).digest('hex') : null;
}

// ---- gameplay: get past loading + menus, then play while capturing distinct frames
const MENU_RX = /^(▶\s*)?(play|start|start game|new game|begin|continue|retry|try again|restart|tap to start|click to start|press start|press any key|ok|next|skip|level ?1|stage ?1|플레이|시작|게임 시작|시작하기|계속|계속하기|다시 시작|다시 하기|재시작|확인|다음|건너뛰기|스킵|1단계|스테이지 ?1)(\b|$|\s)/i;

let THUMB_PAGE = null;
// 32×18 grayscale thumbnail of the viewport — compares screens even when a menu idles with animation
async function thumb(page, box) {
  // compare the game area only: a small canvas on a big empty page would otherwise hide every change
  const clip = box && box.w * box.h > 200 * 150 ? { x: Math.max(0, box.x - box.w / 2), y: Math.max(0, box.y - box.h / 2), width: box.w, height: box.h } : undefined;
  try {
    const b64 = (await page.screenshot({ type: 'jpeg', quality: 30, timeout: 3000, clip })).toString('base64');
    // decode on a separate blank page so the game's own draw-call and audio counters stay untouched
    if (!THUMB_PAGE || THUMB_PAGE.isClosed()) THUMB_PAGE = await page.context().newPage();
    return await THUMB_PAGE.evaluate(async s => {
      const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      const bm = await createImageBitmap(new Blob([u], { type: 'image/jpeg' }));
      const c = document.createElement('canvas'); c.width = 32; c.height = 18;
      const x = c.getContext('2d'); x.drawImage(bm, 0, 0, 32, 18);
      const d = x.getImageData(0, 0, 32, 18).data, g = [];
      for (let i = 0; i < d.length; i += 4) g.push(Math.round(d[i] * 0.3 + d[i + 1] * 0.59 + d[i + 2] * 0.11));
      return g;
    }, b64);
  } catch { return null; }
}
const tdiff = (a, b) => { if (!a || !b || a.length !== b.length) return 1; let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s / a.length / 255; };
const SCENE_CHANGE = 0.08;

async function waitReady(page) {
  // engine loaders (Unity #unity-loading-bar, Godot #status-progress, custom "loading…") must finish before input means anything
  const t = Date.now();
  while (Date.now() - t < 20000) {
    const busy = await page.evaluate(() => {
      const vis = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 2 && r.height > 2 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity) > 0.05; };
      const els = [...document.querySelectorAll('[id*=loading i],[class*=loading i],[id*=loader i],[class*=loader i],#status-progress')];
      return els.some(vis) || /^\s*(loading|로딩)/i.test(document.body?.innerText || '');
    }).catch(() => false);
    if (!busy) break;
    await page.waitForTimeout(500);
  }
  return Date.now() - t;
}

// one attempt to move past the current screen (title, menu, dialog, game over).
// Returns the input that visibly changed the screen, or null when nothing did.
async function menuStep(page, box, input) {
  const W = box ? box.w : 1440, H = box ? box.h : 900, X0 = box ? box.x - W / 2 : 0, Y0 = box ? box.y - H / 2 : 0;
  const base = await thumb(page, box);
  const tries = [
    async () => {
      const label = await input.markStartButton(MENU_RX, RISKY);
      if (!label) return null;
      await page.click('[data-sl-start="1"]', { timeout: 2000 }).catch(() => {});
      await page.evaluate(() => document.querySelectorAll('[data-sl-start]').forEach(e => e.removeAttribute('data-sl-start'))).catch(() => {});
      return '버튼 "' + label + '"';
    },
    // focus the game with a click on an empty corner (a centre click may hit a side menu such as ENDINGS), then the default action
    async () => {
      const focused = await input.click(X0 + W * 0.03, Y0 + H * 0.04);
      await page.waitForTimeout(250);
      const pressed = await input.press('Enter');
      return focused || pressed ? '구석 클릭(포커스)+Enter' : null;
    },
    async () => await input.press('Space') ? 'Space' : null,
    async () => await input.click(X0 + W / 2, Y0 + H / 2) ? '가운데 클릭' : null,
    async () => await input.click(X0 + W / 2, Y0 + H * 0.64) ? '가운데 아래 클릭' : null,
    async () => await input.click(X0 + W / 2, Y0 + H * 0.78) ? '하단 클릭' : null,
    async () => { await input.press('ArrowDown'); await input.press('ArrowUp'); return await input.press('Enter') ? '방향키 선택+Enter' : null; },
    async () => { const z = await input.press('KeyZ'), j = await input.press('KeyJ'); return z || j ? 'Z/J' : null; },
  ];
  for (const act of tries) {
    let name = null;
    try { name = await act(); } catch { name = null; }
    if (!name) continue;
    await page.waitForTimeout(900);
    if (tdiff(base, await thumb(page, box)) > SCENE_CHANGE) return name;
  }
  return null;
}

async function playGame(page, out, guard, docs) {
  const g = { navigations: 0, played_ms: 0 };
  const input = inputPolicy(page);
  const closePopup = p => p.close().catch(() => {});
  page.on('popup', closePopup);
  const onNav = f => { if (f === page.mainFrame()) g.navigations++; };
  page.on('framenavigated', onNav);
  g.loadWaitMs = await waitReady(page);
  const h0 = await canvasHash(page); await page.waitForTimeout(900); const h1 = await canvasHash(page);
  g.animatesIdle = !!(h0 && h1 && h0 !== h1);
  g.hasCanvas = await page.evaluate(() => [...document.querySelectorAll('canvas')].some(c => { const r = c.getBoundingClientRect(); return r.width * r.height > innerWidth * innerHeight * 0.25; })).catch(() => false);
  out.screenshots.game.push(await shot(page, 'game-0-start'));
  const box = await safeEval(page, () => { const c = document.querySelector('canvas'); if (!c) return null; const r = c.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height }; });
  const cx = box ? box.x : 640, cy = box ? box.y : 360;
  // title → menu → level select …: keep stepping while some input visibly changes the screen
  g.menuSteps = []; g.startClicks = [];
  guard.arm();
  const menuStart = Date.now();
  while (g.menuSteps.length < 5 && Date.now() - menuStart < 20000 && !overBudget()) {
    const step = await menuStep(page, box, input);
    if (!step) break;
    g.menuSteps.push(step);
    if (step.startsWith('버튼')) g.startClicks.push(step.slice(4, -1));
    if (g.menuSteps.length <= 3) out.screenshots.game.push(await shot(page, `game-m${g.menuSteps.length}-menu`));
  }
  const R = rng(42), keys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Space', 'KeyW', 'KeyA', 'KeyS', 'KeyD', 'KeyZ', 'KeyX', 'KeyJ', 'Enter'];
  await page.evaluate(() => { if (window.__sl) window.__sl.rec.on = true; }).catch(() => {});
  const start = Date.now();
  let i = 0, nextShot = 1, lastShot = await canvasHash(page), lastCheck = lastShot, checkAt = start + 3000, still = 0;
  g.recoveries = []; g.skippedSameFrames = 0;
  let hBefore = await canvasHash(page);
  let seenChange = false;  // any frame during play that differs from the first (a reload at the end must not hide it)
  const saw = h => { if (h && !hBefore) hBefore = h; else if (h && h !== hBefore) seenChange = true; return h; };
  while (Date.now() - start < PLAY_MS) {
    const k = keys[Math.floor(R() * keys.length)];
    const hold = 120 + R() * 380;
    try { if (!(await within(input.press(k, hold), hold + 2000))) await page.waitForTimeout(hold);
      if (i % 4 === 0 && box) await within(input.click(cx + (R() - 0.5) * box.w * 0.6, cy + (R() - 0.5) * box.h * 0.6), 2000); } catch {}
    const el = Date.now() - start;
    if (nextShot <= 4 && el > PLAY_MS * nextShot / 5) {
      // only keep frames that show something new
      const t = saw(await canvasHash(page));
      if (!t || t !== lastShot) { out.screenshots.game.push(await shot(page, `game-p${nextShot}-play`, { timeout: 4000 })); lastShot = t; }
      else g.skippedSameFrames++;
      nextShot++;
    }
    if (Date.now() > checkAt) {
      // a screen that ignores input for ~6s is a game over / pause / dialog: try to get past it
      const t = saw(await canvasHash(page)); still = t && t === lastCheck ? still + 1 : 0; lastCheck = t; checkAt = Date.now() + 3000;
      if (still >= 2 && g.recoveries.length < 3) { const step = await menuStep(page, box, input); if (step) g.recoveries.push(step); still = 0; }
    }
    i++;
  }
  g.played_ms = Date.now() - start;
  let hAfter = await canvasHash(page);
  for (let n = 0; n < 4 && !hAfter; n++) { await page.waitForTimeout(400); hAfter = await canvasHash(page); }  // caught mid-reload
  saw(hAfter);
  g.changedDuringPlay = seenChange;
  out.screenshots.game.push(await shot(page, 'game-9-end'));
  if (THUMB_PAGE) { await within(THUMB_PAGE.close(), 5000); THUMB_PAGE = null; }
  page.off('framenavigated', onNav);
  const s = await safeEval(page, () => {
    if (!window.__sl) return null;
    const S = window.__sl;
    S.flush?.();
    return { raf: S.raf, intervals: S.intervals, audio: S.audio, dialogs: S.dialogs, draw: S.draw, emojiText: S.emojiText, alpha: S.alpha, shadows: S.shadows, small: S.small };
  }).catch(() => null) || { raf: [], intervals: [], audio: 0, dialogs: [], draw: {}, emojiText: 0, alpha: 0, shadows: 0, small: [] };
  await page.waitForTimeout(100);
  const seen = [...docs.values()];
  if (seen.length > 1 || !Object.keys(s.draw).length) {
    // the game restarted itself: describe the document that drew the most, not the one that happened to be loading
    const total = d => Object.values(d.draw || {}).reduce((a, b) => a + b, 0);
    const best = seen.reduce((a, d) => (!a || total(d) > total(a) ? d : a), null);
    if (best && total(best) > total(s)) Object.assign(s, { draw: best.draw, alpha: best.alpha, shadows: best.shadows });
    s.emojiText = Math.max(s.emojiText, seen.reduce((a, d) => a + d.emojiText, 0));
    g.longestDocFrames = Math.max(0, ...seen.map(d => d.frames));
  }
  s.audio = Math.max(s.audio, seen.reduce((a, d) => a + d.audio, 0));
  if (s) {
    const iv = []; for (let k = 1; k < s.raf.length; k++) iv.push(s.raf[k] - s.raf[k - 1]);
    const sorted = [...iv].sort((a, b) => a - b); const med = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0;
    g.rafFrames = Math.max(s.raf.length, g.longestDocFrames || 0); g.medianFrameMs = +med.toFixed(2); g.fps = med ? Math.round(1000 / med) : 0;
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
  const mix = await safeEval(page, () => {
    const S = window.__sl;
    if (!S || !(S.rec.len > S.rec.sr * 0.5) || !window.__slLib) return null;
    const x = new Float32Array(S.rec.len); let o = 0; for (const c of S.rec.chunks) { x.set(c, o); o += c.length; }
    return window.__slLib.audioFeatures(x, S.rec.sr);
  }).catch(() => null);
  g.sound = soundSummary([...docs.values()].map(d => d.sound), mix);
  // sound files the game loaded, played or not: a short autoplay may trigger only one kind of event
  const loaded = await safeEval(page, () => [...new Set(performance.getEntriesByType('resource').map(e => e.name.split(/[?#]/)[0])
    .filter(n => /\.(wav|mp3|ogg|oga|m4a|aac|flac|webm)$/i.test(n)))]).catch(() => null);
  if (g.sound && loaded) g.sound.loadedSoundFiles = loaded.length;
  g.inputSkipped = input.skipped.n;
  g.requestsBlocked = guard.blocked;
  g.safeMode = !input.free();
  page.off('popup', closePopup);
  return g;
}

/** Sound facts summed over every document of the session, so a reload cannot turn sound into silence. */
function soundSummary(docs, mix) {
  if (!docs.length) return null;  // nothing was observed: unmeasured, which is different from silent
  const sum = k => docs.reduce((a, d) => a + (d[k] || 0), 0);
  const uniq = k => [...new Set(docs.flatMap(d => d[k] || []))];
  const osc = docs.flatMap(d => d.osc || []), types = {};
  for (const [type] of osc) types[type] = (types[type] || 0) + 1;
  return { oscillatorPlays: osc.length, oscillatorTypes: types, distinctSynthVoices: [...new Set(osc.map(o => o.join(':')))].slice(0, 20),
    samplePlays: sum('buffers'), distinctSamples: uniq('kinds').length, sampleRateVariety: uniq('rates').length,
    filters: sum('filters'), reverbs: sum('convolvers'), compressors: sum('compressors'), distortion: sum('shapers'),
    envelopeRamps: sum('ramps'), mediaFiles: uniq('media').slice(0, 10), mediaPlays: sum('mediaPlays'), mix };
}

// The machine doing the measuring: without a GPU (software rasteriser) or on a slow CPU, frame timing describes the
// test machine, not the game.
async function measureMachine(browser) {
  const page = await browser.newPage();
  try {
    const m = await within(page.evaluate(() => {
      const gl = document.createElement('canvas').getContext('webgl');
      const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
      const renderer = gl ? String(ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)) : 'none';
      const runs = [];
      for (let k = 0; k < 5; k++) {
        const t = performance.now(); let x = 0;
        for (let i = 0; i < 3e6; i++) x = (x * 1664525 + 1013904223) | 0;
        runs.push(performance.now() - t + (x & 0));
      }
      runs.sort((a, b) => a - b);
      return { renderer: renderer.slice(0, 160), cpuMs: +runs[2].toFixed(1) };
    }), 8000);
    if (!m) return null;
    m.software = /swiftshader|llvmpipe|softpipe|basic render|software|none/i.test(m.renderer);
    return m;
  } finally { await within(page.close(), 5000); }
}

// ---------------------------------------------------------------- main
let PARTIAL = null;
setTimeout(async () => {
  if (PARTIAL && PARTIAL.desktop) { PARTIAL.ok = true; PARTIAL.partial = true; PARTIAL.notes.push('시간 예산 초과: 측정된 부분까지만 반환'); await emit(PARTIAL); }
  else await emit({ ok: false, error: '렌더 프로브 시간 예산 초과', elapsed_ms: Date.now() - t0 });
  process.exit(0);
}, BUDGET_MS + 60000).unref();

async function main() {
  const out = { ok: false, version: '0.3.0', screenshots: { game: [] }, notes: [] };
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
  out.env = await measureMachine(browser);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, serviceWorkers: 'block', acceptDownloads: false });
  const guard = GUARD = await guardContext(ctx);
  const docs = new Map();  // per-document telemetry, see INSTRUMENT
  let mainPage = null;
  await ctx.exposeBinding('__slFlush', (src, d) => {
    if (src.page !== mainPage || !d || typeof d.doc !== 'string' || !d.sound) return;
    if (docs.has(d.doc) || docs.size < 2000) docs.set(d.doc, d);
  });
  const allDialogs = [];
  await ctx.exposeBinding('__slReport', (_src, d) => { if (allDialogs.length < 30) allDialogs.push(d); });
  await ctx.addInitScript(INSTRUMENT);
  await ctx.addInitScript({ content: LIB });
  const page = mainPage = await ctx.newPage();
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
  out.unbuilt = out.desktop.chars < 20 && await safeEval(page, () => [...document.querySelectorAll('script[type=module][src]')].some(s => /\.(jsx|tsx|ts|vue|svelte)(\?|$)/.test(s.getAttribute('src'))));
  if (out.unbuilt) out.notes.push('빌드되지 않은 소스(JSX/TS 모듈)가 그대로 서빙되어 화면이 비어 있습니다. `npm run dev` 후 그 URL로 검사하세요.');
  const isGame = KIND === 'game' || (KIND === 'auto' && out.desktop.canvasCover >= 0.35 && out.desktop.words < 800 && (out.desktop.buttons || []).length < 25
    && !(out.desktop.docHeight > out.desktop.viewport[1] * 1.6 && (out.desktop.headings || []).length >= 4));  // long, sectioned pages are websites
  out.kindHint = isGame ? 'game' : 'web';
  out.screenshots.desktop = await shot(page, 'desktop');
  out.html = (await stable(page, () => page.content())).slice(0, 1_500_000);
  if (!isGame) {
    // scroll through once so lazy-loaded sections and scroll-in animations render before the full-page capture
    await page.evaluate(async () => { for (let y = 0; y < Math.min(document.documentElement.scrollHeight, 9000); y += innerHeight * 0.8) { scrollTo(0, y); await new Promise(r => setTimeout(r, 250)); } scrollTo(0, 0); }).catch(() => {});
    await page.waitForTimeout(600);
    const fullH = Math.min(out.desktop.docHeight, 9000);
    out.screenshots.desktopFull = await shot(page, 'desktop-full', { fullPage: fullH <= 9000, clip: out.desktop.docHeight > 9000 ? { x: 0, y: 0, width: 1440, height: 9000 } : undefined });
    out.focus = await focusTest(page);
  }
  if (isGame) out.game = await playGame(page, out, guard, docs);
  out.dialogs = allDialogs.slice();
  out.console = { errors: consoleErrors, failed };
  if (!isGame && !overBudget()) {
    const n0 = allDialogs.length;
    guard.arm();
    out.clicks = await clickTest(ctx, url);
    out.clickDialogs = allDialogs.slice(n0);
  }
  // mobile pass
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, serviceWorkers: 'block', acceptDownloads: false });
  GUARD = await guardContext(mctx);
  await mctx.addInitScript(INSTRUMENT);
  const mp = await mctx.newPage();
  await go(mp, url, true);
  await mp.waitForTimeout(600);
  out.mobile = await safeEval(mp, MOBILE);
  out.screenshots.mobile = await shot(mp, 'mobile');
  await Promise.race([Promise.all(assetJobs), new Promise(r => setTimeout(r, 4000))]);
  out.assets = assets;
  await within(mctx.close(), 5000); await within(ctx.close(), 5000); await within(browser.close(), 10000);
  if (server) server.close();
  out.screenshots.game = out.screenshots.game.filter(Boolean);
  out.ok = true; out.elapsed_ms = Date.now() - t0;
  return out;
}

try {
  await emit(await main());
} catch (e) {
  await emit({ ok: false, error: (e && e.message ? e.message : String(e)).split('\n')[0], elapsed_ms: Date.now() - t0 });
}
process.exit(0);
