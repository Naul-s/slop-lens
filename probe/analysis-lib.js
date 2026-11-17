/* SlopLens perception library — injected into pages (browser globals only, no imports).
 * window.__slLib.audioFeatures(samples, sampleRate)  → how a sound is built / how it feels
 * window.__slLib.imageFeatures(imageData)             → pixel-art honesty, palette, alpha edges
 * Everything here describes the OUTPUT a person sees or hears, not the code that made it.
 */
(() => {
  if (window.__slLib) return;

  function fft(re, im) {                       // in-place radix-2
    const n = re.length;
    for (let i = 1, j = 0; i < n; i++) {
      let bit = n >> 1;
      for (; j & bit; bit >>= 1) j ^= bit;
      j ^= bit;
      if (i < j) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; }
    }
    for (let len = 2; len <= n; len <<= 1) {
      const ang = -2 * Math.PI / len, wr = Math.cos(ang), wi = Math.sin(ang);
      for (let i = 0; i < n; i += len) {
        let cr = 1, ci = 0;
        for (let k = 0; k < len / 2; k++) {
          const a = i + k, b = a + len / 2;
          const tr = re[b] * cr - im[b] * ci, ti = re[b] * ci + im[b] * cr;
          re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
          const ncr = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = ncr;
        }
      }
    }
  }

  const db = v => 20 * Math.log10(Math.max(v, 1e-9));
  const pct = (arr, p) => { if (!arr.length) return 0; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };

  /** Describe one sound (or a recorded mix). */
  function audioFeatures(x, sr) {
    const n = x.length, duration = n / sr;
    if (!n) return { duration: 0, silent: true };
    let peak = 0, sum = 0;
    for (let i = 0; i < n; i++) { const a = Math.abs(x[i]); if (a > peak) peak = a; sum += x[i] * x[i]; }
    const rms = Math.sqrt(sum / n);
    if (peak < 1e-4) return { duration, silent: true };
    // 10 ms RMS envelope
    const w = Math.max(1, Math.round(sr * 0.01)), env = [];
    for (let i = 0; i < n; i += w) { let s = 0, m = Math.min(n, i + w); for (let k = i; k < m; k++) s += x[k] * x[k]; env.push(Math.sqrt(s / (m - i))); }
    const emax = Math.max(...env), active = env.map(v => v > emax * 0.05);
    const first = active.indexOf(true), last = active.lastIndexOf(true);
    const reach = env.findIndex(v => v >= emax * 0.9);
    const attackMs = Math.max(0, (reach - first) * 10);
    let lastHigh = -1; env.forEach((v, i) => { if (v >= emax * 0.5) lastHigh = i; });
    const releaseMs = Math.max(0, (last - lastHigh) * 10);
    const activeDb = env.filter((v, i) => active[i]).map(db);
    const dynamicRangeDb = +(pct(activeDb, 0.95) - pct(activeDb, 0.1)).toFixed(1);
    const silenceShare = +(1 - active.filter(Boolean).length / env.length).toFixed(3);
    // body flatness: how constant the level is between attack and release (a held oscillator is flat)
    const body = env.slice(Math.max(reach, 0), Math.max(reach + 1, lastHigh + 1)).map(db);
    const bodyFlat = body.length > 3 ? +(body.filter(v => Math.abs(v - db(emax)) < 3).length / body.length).toFixed(2) : 0;
    // spectrum on the loudest frames
    const N = 4096, frames = [];
    const order = env.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0]).slice(0, 40).map(o => o[1]).sort((a, b) => a - b);
    for (const wi of order) { const st = wi * w; if (st + N <= n && (!frames.length || st - frames[frames.length - 1] > N)) frames.push(st); if (frames.length >= 8) break; }
    if (!frames.length && n >= 256) frames.push(0);
    let purity = 0, flat = 0, centroid = 0, peaks = 0; const f0s = [];
    for (const st of frames) {
      const L = Math.min(N, 1 << Math.floor(Math.log2(Math.min(N, n - st))));
      const re = new Float64Array(L), im = new Float64Array(L);
      for (let k = 0; k < L; k++) re[k] = x[st + k] * (0.5 - 0.5 * Math.cos(2 * Math.PI * k / (L - 1)));
      fft(re, im);
      const mag = new Float64Array(L / 2); let tot = 0, mx = 0, mi = 1, lsum = 0, wsum = 0;
      for (let k = 1; k < L / 2; k++) { const m = re[k] * re[k] + im[k] * im[k]; mag[k] = m; tot += m; if (m > mx) { mx = m; mi = k; } lsum += Math.log(m + 1e-12); wsum += m * k; }
      if (tot <= 0) continue;
      // energy within the 3 strongest spectral peaks (±2 bins) → pure tones score high
      const pk = []; for (let k = 2; k < L / 2 - 2; k++) if (mag[k] > mag[k - 1] && mag[k] >= mag[k + 1] && mag[k] > mx * 0.004) pk.push([mag[k], k]);
      pk.sort((a, b) => b[0] - a[0]);
      let top = 0; for (const [, k] of pk.slice(0, 3)) for (let d = -2; d <= 2; d++) top += mag[k + d] || 0;
      purity += top / tot; flat += Math.exp(lsum / (L / 2 - 1)) / (tot / (L / 2 - 1)); centroid += (wsum / tot) * sr / L; peaks += pk.length;
      f0s.push(mi * sr / L);
    }
    const nf = Math.max(1, frames.length);
    purity /= nf; flat /= nf; centroid /= nf; peaks /= nf;
    const f0mean = f0s.reduce((a, b) => a + b, 0) / Math.max(1, f0s.length);
    const f0drift = f0s.length > 1 ? Math.sqrt(f0s.reduce((a, b) => a + (b - f0mean) ** 2, 0) / f0s.length) / Math.max(1, f0mean) : 0;
    const out = {
      duration: +duration.toFixed(3), peakDb: +db(peak).toFixed(1), rmsDb: +db(rms).toFixed(1), crestDb: +(db(peak) - db(rms)).toFixed(1),
      attackMs, releaseMs, bodyFlat, dynamicRangeDb, silenceShare,
      tonalPurity: +purity.toFixed(3), spectralFlatness: +flat.toFixed(4), centroidHz: Math.round(centroid), spectralPeaks: Math.round(peaks),
      f0Hz: Math.round(f0mean), pitchDrift: +f0drift.toFixed(3),
    };
    // plain-language reading of the numbers
    const tags = [];
    const synthetic = out.tonalPurity > 0.55 && out.spectralPeaks <= 12;
    if (synthetic) tags.push('단일 음색(오실레이터 같은 순음)');
    if (synthetic && out.bodyFlat > 0.6 && duration < 3) tags.push('음량이 일정하게 유지되다 끊김(엔벨로프 없음)');
    if (synthetic && out.releaseMs < 20 && duration < 3) tags.push('여운·잔향 없음');
    if (out.spectralPeaks >= 25 || out.spectralFlatness > 0.05) tags.push('풍부한 배음/노이즈 성분');
    if (duration >= 8 && out.dynamicRangeDb < 6) tags.push('강약 변화가 거의 없음');
    if (duration >= 8) { delete out.attackMs; delete out.releaseMs; delete out.bodyFlat; }  // envelope numbers mean nothing for music
    out.synthetic = synthetic;
    out.tags = tags;
    return out;
  }

  /** Describe one image's pixels (ImageData). */
  function imageFeatures(d) {
    const { width: W, height: H, data } = d;
    let opaque = 0, semi = 0, eq = 0, pairs = 0, sat = 0, lig = 0;
    const colors = new Map(), runs = new Map();
    const hue = new Array(12).fill(0);
    for (let y = 0; y < H; y++) {
      let run = 0, prev = -1;
      for (let x = 0; x < W; x++) {
        const i = (y * W + x) * 4, a = data[i + 3];
        if (a < 16) { if (run >= 2) runs.set(run, (runs.get(run) || 0) + 1); run = 0; prev = -1; continue; }
        if (a < 240) semi++;
        opaque++;
        const key = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
        if (colors.size < 20000) colors.set(key, (colors.get(key) || 0) + 1);
        if (key === prev) { eq++; run++; } else { if (run >= 2) runs.set(run, (runs.get(run) || 0) + 1); run = 1; }
        if (prev !== -1) pairs++;
        prev = key;
        const r = data[i] / 255, g = data[i + 1] / 255, b = data[i + 2] / 255, mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
        const s = mx === mn ? 0 : (l > 0.5 ? (mx - mn) / (2 - mx - mn) : (mx - mn) / (mx + mn));
        sat += s; lig += l;
        if (s > 0.25) { let h = mx === r ? (g - b) / (mx - mn) + (g < b ? 6 : 0) : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4; hue[Math.floor(h * 2) % 12] += s; }
      }
      if (run >= 2) runs.set(run, (runs.get(run) || 0) + 1);
    }
    const blockiness = pairs ? eq / pairs : 0;
    // ---- pixel-grid analysis on luminance edges (tolerant to the noise AI images carry)
    const lum = new Float32Array(W * H), msk = new Uint8Array(W * H);
    for (let i = 0, p = 0; p < W * H; p++, i += 4) { lum[p] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]; msk[p] = data[i + 3] > 128 ? 1 : 0; }
    const colE = new Float64Array(W), rowE = new Float64Array(H);
    // 4x4 tiles of edge energy: generated images spread fine detail evenly over the whole frame,
    // hand-made / art-directed images concentrate it (focal point, flat areas, readable silhouettes)
    const tileE = new Float64Array(16), tileN = new Float64Array(16);
    let lsum = 0, lsq = 0, ln = 0;
    for (let y = 1; y < H; y++) for (let x = 1; x < W; x++) {
      const p = y * W + x; if (!msk[p] || !msk[p - 1] || !msk[p - W]) continue;
      const dx = Math.abs(lum[p] - lum[p - 1]), dy = Math.abs(lum[p] - lum[p - W]);
      colE[x] += dx; rowE[y] += dy;
      const t = Math.min(3, Math.floor(y * 4 / H)) * 4 + Math.min(3, Math.floor(x * 4 / W));
      tileE[t] += dx + dy; tileN[t]++;
      lsum += lum[p]; lsq += lum[p] * lum[p]; ln++;
    }
    const tiles = []; for (let t = 0; t < 16; t++) if (tileN[t] > 50) tiles.push(tileE[t] / tileN[t]);
    const tMean = tiles.length ? tiles.reduce((a, b) => a + b, 0) / tiles.length : 0;
    const tStd = tiles.length ? Math.sqrt(tiles.reduce((a, b) => a + (b - tMean) ** 2, 0) / tiles.length) : 0;
    const detailEvenness = tMean ? +(1 - Math.min(1, tStd / tMean)).toFixed(3) : 0;   // 1 = detail everywhere
    const detailLevel = +tMean.toFixed(2);                                             // mean edge energy per pixel
    const lumStd = ln ? +(Math.sqrt(Math.max(0, lsq / ln - (lsum / ln) ** 2)) / 255).toFixed(3) : 0;
    // a period P whose grid lines (x ≡ phase mod P) carry far more edge energy than chance → blocky "pixel" look
    const comb = (E, P) => { let tot = 0; const ph = new Float64Array(P); for (let i = 0; i < E.length; i++) { ph[i % P] += E[i]; tot += E[i]; } let bi = 0; for (let k = 1; k < P; k++) if (ph[k] > ph[bi]) bi = k; const on = ph[bi] + 0.5 * (ph[(bi + 1) % P] + ph[(bi + P - 1) % P]); return { share: tot ? on / tot : 0, phase: bi }; };
    let P = 0, lift = 0, share = 0, phase = 0;
    for (let k = 3; k <= Math.min(64, Math.floor(W / 6)); k++) {
      const c = comb(colE, k), r = comb(rowE, k), sh = (c.share + r.share) / 2, lf = sh / (2 / k);
      if (lf > lift + 0.15) { lift = lf; P = k; share = sh; phase = c.phase; }
    }
    // a grid of P also lights up at 2P, 3P…: fall back to the smallest divisor that explains the edges as well
    // A finer grid always contains the coarser one's lines, so only switch when the finer grid explains
    // substantially MORE edges (real block d found as 2d: share roughly doubles; spurious d: share barely moves).
    for (let d = 3; d < P; d++) {
      if (P % d) continue;
      const c = comb(colE, d), r = comb(rowE, d), sh = (c.share + r.share) / 2;
      if (sh >= share * (1 + 0.6 * (P / d - 1))) { P = d; share = sh; lift = sh / (2 / d); phase = c.phase; break; }
    }
    // full-screen captures (UI grids, panels) are not pixel art
    const screenLike = W >= 1200 && (Math.abs(W / H - 16 / 9) < 0.05 || Math.abs(W / H - 16 / 10) < 0.03);
    // a pixel-art grid has many cells across the short side; strong straight edges in banners, pipes, buttons
    // or maze screenshots give a coarse period with only a handful of cells (validated 2026-11-17)
    const cellsAcross = P ? Math.min(W, H) / P : 0, aspect = Math.max(W, H) / Math.max(1, Math.min(W, H));
    const pixelLook = lift >= 2.2 && P >= 4 && !screenLike && cellsAcross >= 12 && aspect <= 3;
    // noise inside grid cells: real pixel art cells are flat (≈0), generated "pixel art" cells are noisy
    let cellNoise = 0, cells = 0;
    if (pixelLook) {
      const rph = comb(rowE, P).phase;
      for (let y0 = rph; y0 + P < H; y0 += P) for (let x0 = phase; x0 + P < W; x0 += P) {
        let s = 0, s2 = 0, n = 0;
        for (let y = y0 + 1; y < y0 + P - 1; y++) for (let x = x0 + 1; x < x0 + P - 1; x++) { const p = y * W + x; if (!msk[p]) continue; s += lum[p]; s2 += lum[p] * lum[p]; n++; }
        if (n >= 4) { cellNoise += Math.sqrt(Math.max(0, s2 / n - (s / n) ** 2)); cells++; }
      }
      cellNoise = cells ? cellNoise / cells : 0;
    }
    const out = {
      w: W, h: H, opaqueShare: +(opaque / (W * H)).toFixed(3), semiAlphaShare: opaque ? +(semi / opaque).toFixed(3) : 0,
      colors: colors.size, blockiness: +blockiness.toFixed(3), pixelLook, gridPx: P, gridLift: +lift.toFixed(2),
      offGridEdgeShare: +(1 - share).toFixed(3), cellNoise: +cellNoise.toFixed(2),
      liftCol: P ? +(comb(colE, P).share / (2 / P)).toFixed(2) : 0, liftRow: P ? +(comb(rowE, P).share / (2 / P)).toFixed(2) : 0,
      saturation: opaque ? +(sat / opaque).toFixed(3) : 0, lightness: opaque ? +(lig / opaque).toFixed(3) : 0,
      hues: hue.map(v => +(v / Math.max(1, opaque)).toFixed(3)),
      detailEvenness, detailLevel, lumStd, screenLike,
    };
    const tags = [];
    if (pixelLook && cellsAcross >= 16 && out.colors > 1500 && out.cellNoise > 2.5)
      tags.push(`가짜 픽셀아트: 약 ${P}px 격자처럼 보이지만 칸 내부 노이즈 ${out.cellNoise}, 색 ${out.colors >= 20000 ? '2만+' : out.colors}개 (진짜 픽셀아트는 칸이 단색이고 색이 수십 개)`);
    if (pixelLook && out.colors > 256 && out.offGridEdgeShare > 0.55) tags.push(`픽셀 격자가 불규칙함: 윤곽선의 ${Math.round(out.offGridEdgeShare * 100)}%가 격자에서 벗어남`);
    if (out.semiAlphaShare > 0.25 && pixelLook) tags.push('픽셀아트인데 가장자리가 반투명으로 번짐');
    out.tags = tags;
    return out;
  }

  /** Describe a whole SCREEN's color scheme (screenshot / gameplay frame). */
  function screenFeatures(d) {
    const { width: W, height: H, data } = d, n = W * H;
    const band = { purpleBlue: 0, tealCyan: 0, skyLight: 0, orange: 0, magenta: 0, cream: 0, green: 0, red: 0 };
    let dark = 0, light = 0, sat = 0, prim = 0, satPx = 0;
    const q = new Map();
    for (let i = 0; i < n; i++) {
      const r = data[i * 4] / 255, g = data[i * 4 + 1] / 255, b = data[i * 4 + 2] / 255;
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, dl = mx - mn;
      const s = dl === 0 ? 0 : (l > 0.5 ? dl / (2 - mx - mn) : dl / (mx + mn));
      let h = 0; if (dl) { h = mx === r ? (g - b) / dl + (g < b ? 6 : 0) : mx === g ? (b - r) / dl + 2 : (r - g) / dl + 4; h *= 60; }
      if (l < 0.2) dark++; if (l > 0.85) light++;
      sat += s;
      const key = ((data[i * 4] >> 3) << 10) | ((data[i * 4 + 1] >> 3) << 5) | (data[i * 4 + 2] >> 3);
      q.set(key, (q.get(key) || 0) + 1);
      const ext = [data[i * 4], data[i * 4 + 1], data[i * 4 + 2]].every(v => v <= 25 || v >= 230);
      if (ext && s > 0.8 && l > 0.25 && l < 0.75) prim++;   // pure #ff0000-like UI colors, not tinted blacks/whites
      if (s > 0.22 && l > 0.12 && l < 0.92) {
        satPx++;
        if (h >= 228 && h < 300) band.purpleBlue++;
        if (h >= 170 && h < 215) band.tealCyan++;
        if (h >= 300 && h < 345) band.magenta++;
        if (h >= 12 && h < 42 && s > 0.5) band.orange++;
        if (h >= 75 && h < 160) band.green++;
        if ((h >= 345 || h < 12) && s > 0.5) band.red++;
      }
      if (h >= 180 && h < 220 && l > 0.68 && s > 0.15) band.skyLight++;
      if (h >= 28 && h < 55 && l > 0.78 && s > 0.12 && s < 0.7) band.cream++;
    }
    const top = [...q.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([k, c]) => {
      const R = (k >> 10) << 3, G = ((k >> 5) & 31) << 3, B = (k & 31) << 3;
      return { hex: '#' + [R, G, B].map(v => v.toString(16).padStart(2, '0')).join(''), share: +(c / n).toFixed(3) };
    });
    const out = { darkShare: +(dark / n).toFixed(3), lightShare: +(light / n).toFixed(3), meanSat: +(sat / n).toFixed(3),
      saturatedShare: +(satPx / n).toFixed(3), primaryShare: +(prim / n).toFixed(4), topColors: top, dominantShare: top[0] ? top[0].share : 0 };
    for (const k in band) out[k] = +(band[k] / n).toFixed(3);
    return out;
  }

  window.__slLib = { fft, audioFeatures, imageFeatures, screenFeatures };
})();
