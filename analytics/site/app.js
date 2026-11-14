/* Instagram 分析サイト（静的）。data/ の JSON を読み、ブラウザの中だけで集計して表示する。
   データの形は analytics/SCHEMA.md を参照。 */
'use strict';

/* ================= 日付の道具 ================= */
const DAY = 864e5;
const dn = s => Math.round(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) / DAY);
const ds = n => new Date(n * DAY).toISOString().slice(0, 10);
const todayDn = () => Math.floor((Date.now() + 9 * 3600e3) / DAY);
const wdOf = n => (new Date(n * DAY).getUTCDay() + 6) % 7; // 月=0
const WD = ['月', '火', '水', '木', '金', '土', '日'];
const mdj = n => { const d = new Date(n * DAY); return `${d.getUTCMonth() + 1}月${d.getUTCDate()}日`; };
const mds = n => { const d = new Date(n * DAY); return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`; };
const ymd = n => ds(n).replace(/-/g, '/');
const monthOf = n => ds(n).slice(0, 7);
const addYears = (n, y) => { const d = new Date(n * DAY); d.setUTCFullYear(d.getUTCFullYear() + y); return Math.round(d.getTime() / DAY); };
const monthStart = n => { const d = new Date(n * DAY); return Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1) / DAY); };
function monthsBetween(a, b) { const out = []; let m = monthStart(a); while (m <= b) { out.push(monthOf(m)); const d = new Date(m * DAY); m = Math.round(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1) / DAY); } return out; }
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

/* ================= 指標の定義 ================= */
const REACH_NOTE = '期間の値は日ごとの値を足したもので、別の日に同じ人が見た分は重ねて数えます。';
const M = {
  reach: { l: 'リーチ', t: '見た人の数。同じ人が何回見ても1人と数えます。' + REACH_NOTE },
  views: { l: '表示回数', t: '画面に表示された回数。同じ人が何回見ても、そのたびに数えます。' },
  likes: { l: 'いいね', t: 'いいねされた数。' },
  comments: { l: 'コメント', t: 'コメントされた数。' },
  saves: { l: '保存', t: 'あとで見返すために保存された数。役に立つと思われた投稿ほど増えます。' },
  shares: { l: 'シェア', t: 'ほかの人に送られたり、ストーリーズで紹介されたりした数。' },
  follows: { l: 'フォロー', t: 'その投稿を見てフォローした人の数。' },
  profile_visits: { l: 'プロフィールへのアクセス', t: 'その投稿からプロフィールを見に来た数。' },
  interactions: { l: '反応の合計', t: 'いいね・コメント・保存・シェアを足した数。' },
  eng_rate: { l: '反応率', t: '反応の合計 ÷ リーチ。見た人のうち、どれだけの人が反応したかの割合です。', f: 'pct', ratio: ['interactions', 'reach'] },
  save_rate: { l: '保存率', t: '保存 ÷ リーチ。見た人のうち、保存した人の割合です。', f: 'pct', ratio: ['saves', 'reach'] },
  posts: { l: '投稿数', t: '選んだ期間に投稿した数。' },
  avg_watch: { l: '平均視聴時間', t: 'リールが1回再生されたときに見られた平均の秒数（リールだけ）。表示回数で重みをつけた平均です。', f: 'sec', wavg: true },
  skip_rate: { l: 'スキップ率', t: 'リールが最初の数秒で飛ばされた割合（リールだけ）。低いほど良い指標です。', f: 'pct1', wavg: true, down: true },
  followers: { l: 'フォロワー数', t: 'その日の終わりのフォロワーの数。期間の値は最終日の数です。', last: true },
  follows_new: { l: '新しいフォロー', t: 'その期間にフォローしてくれた人の数。' },
  unfollows: { l: 'フォロー解除', t: 'その期間にフォローをやめた人の数。少ないほど良い指標です。', down: true },
  net_follows: { l: 'フォロワーの純増', t: '新しいフォロー − フォロー解除。' },
  profile_views: { l: 'プロフィールの表示', t: 'プロフィールのページが見られた回数。' },
  website_clicks: { l: 'ウェブサイトのクリック', t: 'プロフィールに載せたリンクが押された回数。' },
  accounts_engaged: { l: '反応した人', t: 'いいね・コメント・保存・シェアなどをした人の数。' + REACH_NOTE },
  total_interactions: { l: '反応の合計', t: 'いいね・コメント・保存・シェアなどを足した数。' },
  acc_eng_rate: { l: '反応率', t: '反応の合計 ÷ リーチ。', f: 'pct', ratio: ['total_interactions', 'reach'] },
  count: { l: 'フォロワー数', t: 'その区分にあたるフォロワーの数（記録した日の時点）。' },
  online: { l: 'オンラインのフォロワー', t: 'その曜日・時刻に Instagram を開いていたフォロワーの数（平均）。', avg: true },
  c_followers: { l: 'フォロワー数', t: '記録した日のフォロワーの数。期間の値は最後に記録した日の数です。', last: true },
  c_growth: { l: 'フォロワーの増減', t: '期間の最初と最後に記録したフォロワー数の差。', delta: 'c_followers' },
  c_ppw: { l: '週あたりの投稿数', t: '直近の投稿から計算した、1週間あたりの投稿の数。', last: true, f: 'dec1' },
  c_avg_likes: { l: '平均いいね', t: '直近の投稿1本あたりの、いいねの平均。', last: true, f: 'dec1' },
  c_avg_comments: { l: '平均コメント', t: '直近の投稿1本あたりの、コメントの平均。', last: true, f: 'dec1' },
  c_er: { l: '反応率', t: '（平均いいね＋平均コメント）÷ フォロワー数。', last: true, f: 'pct1' },
  c_reel: { l: 'リールの割合', t: '直近の投稿のうち、リールの割合。', last: true, f: 'pct1' },
  c_media: { l: '投稿の総数', t: 'これまでに投稿した数の合計。', last: true },
  top_likes: { l: 'いいね', t: '記録した日の時点のいいねの数。' },
  top_comments: { l: 'コメント', t: '記録した日の時点のコメントの数。' },
};
const PM = ['reach', 'views', 'likes', 'comments', 'saves', 'shares', 'follows', 'profile_visits']; // 累計の指標
const CONTENT_METRICS = ['posts', 'reach', 'views', 'interactions', 'eng_rate', 'likes', 'comments', 'saves', 'save_rate', 'shares', 'follows', 'profile_visits', 'avg_watch', 'skip_rate'];
const CONTENT_TABLE = ['posts', 'reach', 'views', 'interactions', 'eng_rate', 'saves', 'shares', 'follows', 'profile_visits', 'avg_watch', 'skip_rate'];
const ACC_METRICS = ['reach', 'views', 'profile_views', 'website_clicks', 'accounts_engaged', 'total_interactions', 'acc_eng_rate', 'followers', 'follows_new', 'unfollows', 'net_follows'];
const STYLE_NAME = { screen: 'スマホ操作型', telop: '大きな文字の型', photo: '写真ストーリーの型' };
const GENDER = { F: '女性', M: '男性', U: '不明' };

function fmt(k, v) {
  if (v == null || (typeof v === 'number' && !isFinite(v))) return '—';
  const f = M[k] && M[k].f;
  if (f === 'pct') return (v * 100).toFixed(2) + '%';
  if (f === 'pct1') return v.toFixed(1) + '%';
  if (f === 'sec') return v.toFixed(1) + '秒';
  if (f === 'dec1') return v.toLocaleString('ja-JP', { maximumFractionDigits: 1 });
  return Math.round(v).toLocaleString('ja-JP');
}
function axisFmt(k) {
  const f = M[k] && M[k].f;
  return v => f === 'pct' ? (v * 100).toFixed(1) + '%' : f === 'pct1' ? v + '%' : f === 'sec' ? v + '秒' : Number(v).toLocaleString('ja-JP');
}
function tipAttr(k) { return M[k] ? ` data-tip="${esc(M[k].t)}" data-tip-title="${esc(M[k].l)}"` : ''; }
function chgHtml(k, cur, prev) {
  if (cur == null || prev == null || prev === 0) return '<span class="chg flat">—</span>';
  const r = (cur - prev) / Math.abs(prev);
  if (Math.abs(r) < 0.0005) return '<span class="chg flat">0.0%</span>';
  const good = M[k] && M[k].down ? r < 0 : r > 0;
  return `<span class="chg ${good ? 'up' : 'down'}">${r > 0 ? '↑' : '↓'} ${Math.abs(r * 100).toFixed(1)}%</span>`;
}

/* 集計: 行の配列から指標の値を出す */
function sumOf(rows, k) { let s = 0; for (const r of rows) { const v = r[k]; if (v != null) s += v; } return s; }
function agg(rows, keys) {
  const o = {};
  const need = new Set();
  keys.forEach(k => { need.add(k); if (M[k] && M[k].ratio) M[k].ratio.forEach(x => need.add(x)); if (M[k] && M[k].delta) need.add(M[k].delta); });
  for (const k of need) {
    const d = M[k] || {};
    if (d.ratio) continue;
    if (d.wavg) {
      let s = 0, w = 0, s2 = 0, n2 = 0;
      for (const r of rows) {
        const v = r[k]; if (v == null) continue;
        const ww = r['_w_' + k] || 0; s += v * ww; w += ww; s2 += v; n2++;
      }
      o[k] = w > 0 ? s / w : (n2 ? s2 / n2 : null);
      o['_w_' + k] = w;
    } else if (d.avg) {
      let s = 0, n = 0; for (const r of rows) if (r[k] != null) { s += r[k]; n++; } o[k] = n ? s / n : null;
    } else if (d.last) {
      let mx = -Infinity, vals = [];
      for (const r of rows) { if (r[k] == null) continue; if (r._d > mx) { mx = r._d; vals = [r[k]]; } else if (r._d === mx) vals.push(r[k]); }
      o[k] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
    } else if (d.delta) {
      const src = d.delta; let mx = -Infinity, mn = Infinity, vx = null, vn = null;
      for (const r of rows) { if (r[src] == null) continue; if (r._d > mx) { mx = r._d; vx = r[src]; } if (r._d < mn) { mn = r._d; vn = r[src]; } }
      o[k] = vx == null ? null : vx - vn;
    } else o[k] = rows.length ? sumOf(rows, k) : 0;
  }
  for (const k of keys) { const d = M[k]; if (d && d.ratio) { const den = o[d.ratio[1]]; o[k] = den ? o[d.ratio[0]] / den : null; } }
  return o;
}

/* ================= 状態 ================= */
const S = {
  accounts: [], acc: null, D: {}, report: 'home',
  range: null, preset: '28d', cmp: { on: true, mode: 'prev', start: null, end: null },
  ch: {}, tb: {}, home: { kpi: 'reach' }, charts: [],
};
const store = {
  get(k) { try { return localStorage.getItem('igana_' + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem('igana_' + k, v); } catch (e) { /* 使えなくても動く */ } },
};

const NAV = [
  { id: 'home', label: 'ホーム', icon: 'M3 11l9-8 9 8v10h-6v-6H9v6H3z' },
  { id: 'realtime', label: 'リアルタイム（直近の投稿）', icon: 'M12 3a9 9 0 100 18 9 9 0 000-18zm1 4h-2v6l5 3 1-1.7-4-2.3z' },
  { sep: true },
  { group: 'オーディエンス', icon: 'M9 11a4 4 0 100-8 4 4 0 000 8zm8 0a3 3 0 100-6 3 3 0 000 6zM1 21v-2c0-3 4-5 8-5s8 2 8 5v2zm17 0v-2c0-1.4-.6-2.6-1.6-3.5 2.9.4 5.6 1.7 5.6 3.5v2z', items: [
    ['aud-overview', '概要'], ['aud-followers', 'フォロワーの増減'], ['aud-demo', '性別・年代'], ['aud-geo', '地域'], ['aud-online', 'オンラインの時間帯']] },
  { group: 'コンテンツ', icon: 'M4 3h16v18H4zm3 4v2h10V7zm0 4v2h10v-2zm0 4v2h6v-2z', items: [
    ['content-all', 'すべての投稿'], ['content-format', '形式別'], ['content-topic', '話題別'], ['content-style', 'リールの型別'], ['content-time', '曜日と時刻']] },
  { group: '競合', icon: 'M4 21V4h2v1h12l-2 4 2 4H6v8z', items: [
    ['comp-overview', '概要'], ['comp-trend', '推移'], ['comp-posts', '投稿の比較']] },
  { sep: true },
  { id: 'review', label: '確認待ち', icon: 'M9 16.2l-3.5-3.5L4 14.2l5 5 11-11-1.5-1.5z', soon: true },
];
function navInfo(id) {
  for (const n of NAV) {
    if (n.id === id) return { group: '', label: n.label };
    if (n.items) for (const [i, l] of n.items) if (i === id) return { group: n.group, label: l };
  }
  return null;
}

/* ================= データ読み込み ================= */
async function getJSON(path) {
  const r = await fetch(path, { cache: 'no-cache' });
  if (!r.ok) throw new Error(path + ' を読めませんでした（' + r.status + '）');
  return r.json();
}
async function loadAccount(acc) {
  if (S.D[acc.id]) return S.D[acc.id];
  const base = 'data/' + acc.id + '/';
  const opt = p => getJSON(base + p).catch(() => null);
  const [daily, posts, aud, comp, review] = await Promise.all([opt('daily.json'), opt('posts.json'), opt('audience.json'), opt('competitors.json'), opt('review.json')]);
  const D = {
    acc, recStart: dn(acc.record_start), last: dn(acc.last_date),
    daily: ((daily && daily.days) || []).map(d => Object.assign({}, d, { _d: dn(d.date), net_follows: (d.follows_new || 0) - (d.unfollows || 0) })).sort((a, b) => a._d - b._d),
    posts: ((posts && posts.posts) || []).map(p => Object.assign({}, p, { _d: dn(p.date), _h: p.time ? +p.time.slice(0, 2) : null })).sort((a, b) => a._d - b._d || String(a.time).localeCompare(String(b.time))),
    aud: ((aud && aud.snapshots) || []).map(s => Object.assign({}, s, { _d: dn(s.date) })).sort((a, b) => a._d - b._d),
    comp: comp || { competitors: [], snapshots: [] },
    review: (review && review.items) || [],
    months: new Set(), C: {},
  };
  D.comp.snapshots.forEach(s => { s._d = dn(s.date); });
  D.postById = Object.fromEntries(D.posts.map(p => [p.id, p]));
  S.D[acc.id] = D;
  return D;
}
async function ensureMonths(D, months) {
  const avail = new Set(D.acc.post_daily_months || []);
  const todo = months.filter(m => avail.has(m) && !D.months.has(m));
  const res = await Promise.all(todo.map(m => getJSON('data/' + D.acc.id + '/post_daily/' + m + '.json').then(j => [m, j])));
  for (const [m, j] of res) {
    const mi = j.metrics; D.months.add(m);
    for (const row of j.rows) {
      const pid = row[0], d = dn(row[1]);
      const vals = {}; mi.forEach((k, i) => { vals[k] = row[2 + i]; });
      let c = D.C[pid]; if (!c) c = D.C[pid] = { rows: new Map(), first: d, last: d };
      c.rows.set(d, vals); if (d < c.first) c.first = d; if (d > c.last) c.last = d;
    }
  }
}
function neededMonths(D) {
  const ranges = [[S.range[0] - 1, S.range[1]]];
  if (S.cmp.on) ranges.push([S.cmp.start - 1, S.cmp.end]);
  const set = new Set([monthOf(D.recStart)]);
  for (const [a, b] of ranges) monthsBetween(Math.max(a, D.recStart), Math.min(b, D.last)).forEach(m => set.add(m));
  return [...set];
}

/* 投稿の累計 → 期間の値 */
function cumAt(D, pid, x) {
  const c = D.C[pid]; if (!c) return null;
  if (x > c.last) x = c.last;
  for (let d = x; d >= c.first; d--) { const r = c.rows.get(d); if (r) return r; }
  return null;
}
function baseBefore(D, p, x) {
  const r = cumAt(D, p.id, x - 1); if (r) return r;
  const c = D.C[p.id];
  if (c && p._d < D.recStart && x - 1 < c.first) return c.rows.get(c.first); // 記録開始前の投稿は、最初の記録を起点にする
  return null;
}
function postDelta(D, p, a, b) {
  const e = cumAt(D, p.id, b); const o = {};
  if (!e || p._d > b) { PM.forEach(k => { o[k] = 0; }); o.avg_watch = null; o.skip_rate = null; return o; }
  const s = baseBefore(D, p, a);
  PM.forEach(k => { o[k] = Math.max(0, (e[k] || 0) - ((s && s[k]) || 0)); });
  o.avg_watch = e.reel_avg_watch_sec == null ? null : e.reel_avg_watch_sec;
  o.skip_rate = e.reel_skip_rate == null ? null : e.reel_skip_rate;
  return o;
}
function postRow(D, p, a, b) {
  const o = postDelta(D, p, a, b);
  o.interactions = o.likes + o.comments + o.saves + o.shares;
  o.posts = p._d >= a && p._d <= b ? 1 : 0;
  o._w_avg_watch = o.avg_watch == null ? 0 : o.views; o._w_skip_rate = o._w_avg_watch;
  o._p = p; o._d = p._d;
  return o;
}
function contentRows(D, a, b) {
  const out = [];
  for (const p of D.posts) { if (p._d > b) continue; const r = postRow(D, p, a, b); if (r.posts || r.reach > 0 || r.views > 0) out.push(r); }
  return out;
}
function contentDays(D, a, b, filter) {
  const days = [];
  for (let x = a; x <= b; x++) {
    const rows = [];
    for (const p of D.posts) { if (p._d > x) break; if (filter && !filter(p)) continue; rows.push(postRow(D, p, x, x)); }
    const o = agg(rows, CONTENT_METRICS); o._d = x; days.push(o);
  }
  return days;
}
function accountDays(D, a, b) { return D.daily.filter(d => d._d >= a && d._d <= b); }
function clip(D, a, b) { const s = Math.max(a, D.recStart), e = Math.min(b, D.last); return s <= e ? [s, e] : null; }

/* ================= 期間 ================= */
function presetRange(id) {
  const T = todayDn();
  switch (id) {
    case 'today': return [T, T];
    case 'yesterday': return [T - 1, T - 1];
    case '7d': return [T - 7, T - 1];
    case '28d': return [T - 28, T - 1];
    case '90d': return [T - 90, T - 1];
    case 'month': return [monthStart(T), T];
    case 'lastmonth': { const e = monthStart(T) - 1; return [monthStart(e), e]; }
    default: return null;
  }
}
const PRESETS = [['today', '今日'], ['yesterday', '昨日'], ['7d', '過去7日間'], ['28d', '過去28日間'], ['90d', '過去90日間'], ['month', '今月'], ['lastmonth', '先月'], ['custom', 'カスタム']];
function cmpRange(mode, a, b, cs, ce) {
  if (mode === 'prev') { const len = b - a + 1; return [a - len, a - 1]; }
  if (mode === 'yoy') return [addYears(a, -1), addYears(b, -1)];
  return [cs, ce];
}
function applyCmp() { if (S.cmp.mode !== 'custom') { const [cs, ce] = cmpRange(S.cmp.mode, S.range[0], S.range[1]); S.cmp.start = cs; S.cmp.end = ce; } }
function drLabel() {
  $('#drMain').textContent = `${ymd(S.range[0])} 〜 ${ymd(S.range[1])}`;
  $('#drCmp').textContent = S.cmp.on ? `比較: ${ymd(S.cmp.start)} 〜 ${ymd(S.cmp.end)}` : '';
}
function openDr() {
  const p = $('#drPanel');
  const t = { preset: S.preset, a: S.range[0], b: S.range[1], on: S.cmp.on, mode: S.cmp.mode, cs: S.cmp.start, ce: S.cmp.end };
  p.innerHTML = `
    <div class="row"><label class="lab" for="drPreset">期間</label>
      <select id="drPreset">${PRESETS.map(([v, l]) => `<option value="${v}"${v === t.preset ? ' selected' : ''}>${l}</option>`).join('')}</select></div>
    <div class="row"><label class="lab" for="drA">開始日</label><input type="date" id="drA" value="${ds(t.a)}"></div>
    <div class="row"><label class="lab" for="drB">終了日</label><input type="date" id="drB" value="${ds(t.b)}"></div>
    <div class="hint">記録がある期間: ${ymd(curD().recStart)} 〜 ${ymd(curD().last)}</div>
    <div class="sep"></div>
    <div class="row"><label><input type="checkbox" id="drOn"${t.on ? ' checked' : ''}> 比較する</label>
      <select id="drMode"${t.on ? '' : ' disabled'}>
        <option value="prev"${t.mode === 'prev' ? ' selected' : ''}>前の期間</option>
        <option value="yoy"${t.mode === 'yoy' ? ' selected' : ''}>前年同期</option>
        <option value="custom"${t.mode === 'custom' ? ' selected' : ''}>カスタム</option></select></div>
    <div class="row"><label class="lab" for="drCs">比較の開始</label><input type="date" id="drCs"></div>
    <div class="row"><label class="lab" for="drCe">比較の終了</label><input type="date" id="drCe"></div>
    <div class="btns"><button class="btn primary" id="drOk">適用</button><button class="btn" id="drNo">キャンセル</button></div>`;
  const sync = () => {
    const a = dn($('#drA').value || ds(t.a)), b = dn($('#drB').value || ds(t.b));
    const on = $('#drOn').checked, mode = $('#drMode').value;
    $('#drMode').disabled = !on;
    if (mode !== 'custom') { const [cs, ce] = cmpRange(mode, a, b); $('#drCs').value = ds(cs); $('#drCe').value = ds(ce); }
    else if (!$('#drCs').value) { const [cs, ce] = cmpRange('prev', a, b); $('#drCs').value = ds(cs); $('#drCe').value = ds(ce); }
    $('#drCs').disabled = $('#drCe').disabled = !on || mode !== 'custom';
  };
  $('#drPreset').onchange = () => { const r = presetRange($('#drPreset').value); if (r) { $('#drA').value = ds(r[0]); $('#drB').value = ds(r[1]); } sync(); };
  $('#drA').onchange = $('#drB').onchange = () => { $('#drPreset').value = 'custom'; sync(); };
  $('#drOn').onchange = $('#drMode').onchange = sync;
  if (t.mode === 'custom') { $('#drCs').value = ds(t.cs); $('#drCe').value = ds(t.ce); }
  sync();
  $('#drOk').onclick = () => {
    let a = dn($('#drA').value), b = dn($('#drB').value);
    if (isNaN(a) || isNaN(b)) return toast('日付を入れてください');
    if (a > b) [a, b] = [b, a];
    S.preset = $('#drPreset').value; S.range = [a, b];
    S.cmp.on = $('#drOn').checked; S.cmp.mode = $('#drMode').value;
    if (S.cmp.mode === 'custom') { let cs = dn($('#drCs').value), ce = dn($('#drCe').value); if (isNaN(cs) || isNaN(ce)) return toast('比較の日付を入れてください'); if (cs > ce) [cs, ce] = [ce, cs]; S.cmp.start = cs; S.cmp.end = ce; }
    else applyCmp();
    closeDr(); drLabel(); render();
  };
  $('#drNo').onclick = closeDr;
  p.hidden = false; $('#drBtn').setAttribute('aria-expanded', 'true');
}
function closeDr() { $('#drPanel').hidden = true; $('#drBtn').setAttribute('aria-expanded', 'false'); }

/* ================= 共通の部品 ================= */
function curD() { return S.D[S.acc]; }
function destroyCharts(scope) { S.charts = S.charts.filter(c => { if (!scope || c._scope === scope) { c.destroy(); return false; } return true; }); }
function mkChart(canvas, cfg, scope) {
  if (typeof Chart === 'undefined') { canvas.parentNode.innerHTML = '<div class="muted small">グラフの部品を読み込めませんでした（インターネット接続を確認してください）</div>'; return null; }
  const c = new Chart(canvas, cfg); c._scope = scope || 'page'; S.charts.push(c); return c;
}
function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; document.body.appendChild(t); setTimeout(() => t.remove(), 2200); }
function metricOptions(keys, sel, none) {
  return (none ? '<option value="">なし</option>' : '') + keys.map(k => `<option value="${k}"${k === sel ? ' selected' : ''}>${esc(M[k].l)}</option>`).join('');
}
const C1 = '#1e6fd9', C2 = '#e8710a';
const SERIES_COLORS = ['#1e6fd9', '#e8710a', '#188038', '#9334e6', '#d93025', '#12a4af', '#f9ab00', '#5f6368'];

/* 日/週/月にまとめる */
function bucket(days, gran, keys) {
  const groups = [];
  let cur = null;
  for (const d of days) {
    let key, label;
    if (gran === 'week') { const ws = d._d - wdOf(d._d); key = ws; label = mds(Math.max(ws, days[0]._d)) + '〜'; }
    else if (gran === 'month') { key = monthOf(d._d); label = key.replace('-', '年') + '月'; }
    else { key = d._d; label = mds(d._d) + '(' + WD[wdOf(d._d)] + ')'; }
    if (!cur || cur.key !== key) { cur = { key, label, start: d._d, rows: [] }; groups.push(cur); }
    cur.rows.push(d);
  }
  return groups.map(g => ({ label: g.label, start: g.start, v: agg(g.rows, keys) }));
}

/* 折れ線グラフ（UA のレポート上部） */
function trendChart(el, cfg) {
  const st = S.ch[cfg.id] || (S.ch[cfg.id] = { m1: cfg.m1, m2: cfg.m2 || '', gran: 'day' });
  if (!cfg.metrics.includes(st.m1)) st.m1 = cfg.metrics[0];
  el.innerHTML = `
    <div class="ctrl">
      <select class="m1" aria-label="指標">${metricOptions(cfg.metrics, st.m1)}</select>
      <span class="vs">と比べる指標</span>
      <select class="m2" aria-label="重ねる指標">${metricOptions(cfg.metrics, st.m2, true)}</select>
      <span class="grow"></span>
      <div class="seg" role="group" aria-label="まとめる単位">
        ${[['day', '日'], ['week', '週'], ['month', '月']].map(([v, l]) => `<button data-g="${v}" class="${st.gran === v ? 'on' : ''}">${l}</button>`).join('')}
      </div>
    </div>
    <div class="legend"></div>
    <div class="chart-wrap"><canvas></canvas></div>`;
  const draw = () => {
    destroyCharts(cfg.id);
    const keys = [st.m1, st.m2].filter(Boolean);
    const cur = bucket(cfg.days, st.gran, keys);
    const cmp = cfg.cmpDays && cfg.cmpDays.length ? bucket(cfg.cmpDays, st.gran, keys) : null;
    const ds_ = [];
    const mk = (k, data, color, axis, dashed, label) => ({
      label, data, borderColor: color, backgroundColor: dashed ? 'transparent' : (axis === 'y' ? 'rgba(30,111,217,.10)' : 'transparent'),
      fill: !dashed && axis === 'y', borderWidth: dashed ? 1.5 : 2, borderDash: dashed ? [5, 4] : [], pointRadius: cur.length > 40 ? 0 : 2.5,
      pointHoverRadius: 4, tension: 0.15, yAxisID: axis, _k: k, _cmp: dashed,
    });
    ds_.push(mk(st.m1, cur.map(g => g.v[st.m1]), C1, 'y', false, M[st.m1].l));
    if (cmp) ds_.push(mk(st.m1, cur.map((_, i) => cmp[i] ? cmp[i].v[st.m1] : null), C1, 'y', true, M[st.m1].l + '（比較期間）'));
    if (st.m2) {
      ds_.push(mk(st.m2, cur.map(g => g.v[st.m2]), C2, 'y1', false, M[st.m2].l));
      if (cmp) ds_.push(mk(st.m2, cur.map((_, i) => cmp[i] ? cmp[i].v[st.m2] : null), C2, 'y1', true, M[st.m2].l + '（比較期間）'));
    }
    $('.legend', el).innerHTML = ds_.map(d => `<span><i class="${d._cmp ? 'dash' : ''}" style="border-color:${d.borderColor}"></i>${esc(d.label)}</span>`).join('');
    const scales = {
      x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8, color: '#5f6368', font: { size: 11 } } },
      y: { beginAtZero: true, grid: { color: '#eeeeee' }, ticks: { color: '#5f6368', font: { size: 11 }, callback: axisFmt(st.m1), maxTicksLimit: 5 } },
    };
    if (st.m2) scales.y1 = { position: 'right', beginAtZero: true, grid: { display: false }, ticks: { color: '#5f6368', font: { size: 11 }, callback: axisFmt(st.m2), maxTicksLimit: 5 } };
    mkChart($('canvas', el), {
      type: 'line', data: { labels: cur.map(g => g.label), datasets: ds_ },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { callbacks: {
          title: items => items.length ? cur[items[0].dataIndex].label : '',
          label: it => { const d = it.dataset; const extra = d._cmp && cmp && cmp[it.dataIndex] ? '（' + cmp[it.dataIndex].label + '）' : ''; return ` ${d.label}${extra}: ${fmt(d._k, it.raw)}`; },
        } } },
        scales,
      },
    }, cfg.id);
  };
  $('.m1', el).onchange = e => { st.m1 = e.target.value; draw(); if (cfg.onMetric) cfg.onMetric(st.m1); };
  $('.m2', el).onchange = e => { st.m2 = e.target.value; draw(); };
  $$('.seg button', el).forEach(b => { b.onclick = () => { st.gran = b.dataset.g; $$('.seg button', el).forEach(x => x.classList.toggle('on', x === b)); draw(); }; });
  draw();
  return { setMetric(k) { st.m1 = k; $('.m1', el).value = k; draw(); } };
}

function sparkSvg(vals) {
  const v = vals.map(x => x == null ? 0 : x); if (v.length < 2) return '';
  const mx = Math.max(...v), mn = Math.min(...v), W = 80, H = 22, r = mx - mn || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 2 - (x - mn) / r * (H - 4)).toFixed(1)}`).join(' ');
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${C1}" stroke-width="1.5"/></svg>`;
}
function scorecards(el, cfg) {
  const cur = agg(cfg.days, cfg.keys), cmp = cfg.cmpDays && cfg.cmpDays.length ? agg(cfg.cmpDays, cfg.keys) : null;
  const sel = cfg.selected && cfg.selected();
  el.innerHTML = cfg.keys.map(k => `
    <div class="score${k === sel ? ' on' : ''}" data-k="${k}" tabindex="0" role="button" aria-label="${esc(M[k].l)}をグラフに出す">
      <div class="lab"${tipAttr(k)}>${esc(M[k].l)}</div>
      <div class="val">${fmt(k, cur[k])}</div>
      <div class="bot">${cmp ? chgHtml(k, cur[k], cmp[k]) : '<span></span>'}${sparkSvg(cfg.days.map(d => d[k]))}</div>
    </div>`).join('');
  $$('.score', el).forEach(s => {
    const go = () => { if (cfg.onPick) { cfg.onPick(s.dataset.k); $$('.score', el).forEach(x => x.classList.toggle('on', x === s)); } };
    s.onclick = go; s.onkeydown = e => { if (e.key === 'Enter') go(); };
  });
}

/* ================= 表（エクスプローラー） ================= */
function explorer(el, cfg) {
  const st = S.tb[cfg.id] || (S.tb[cfg.id] = { dim: cfg.dim || cfg.dims[0].key, dim2: '', sort: null, q: '', qmode: 'in', n: 10, page: 0, view: 'table', vm: null });
  if (!cfg.dims.find(d => d.key === st.dim)) st.dim = cfg.dims[0].key;
  const metrics = cfg.metrics;
  if (!st.vm || !metrics.includes(st.vm)) st.vm = cfg.pieMetric || metrics.find(k => !(M[k].ratio || M[k].wavg || M[k].last || M[k].avg)) || metrics[0];
  const addable = metrics.filter(k => !(M[k].ratio || M[k].wavg || M[k].last || M[k].avg || M[k].delta));
  const dimOf = k => cfg.dims.find(d => d.key === k);

  function group(rows, ctx) {
    const d1 = dimOf(st.dim), d2 = st.dim2 ? dimOf(st.dim2) : null;
    const g = new Map();
    for (const r of rows) {
      const v1 = d1.get(r, ctx); if (v1 == null) continue;
      const v2 = d2 ? d2.get(r, ctx) : null; if (d2 && v2 == null) continue;
      const key = v1.k + '\u0001' + (v2 ? v2.k : '');
      let o = g.get(key); if (!o) { o = { key, l1: v1.l, o1: v1.o, l2: v2 ? v2.l : '', o2: v2 ? v2.o : null, rows: [], ref: r }; g.set(key, o); }
      o.rows.push(r);
    }
    for (const o of g.values()) o.v = agg(o.rows, metrics);
    return g;
  }
  function draw() {
    destroyCharts('x-' + cfg.id);
    const ctx = { start: S.eff.cur[0] }, cctx = { start: S.eff.cmp ? S.eff.cmp[0] : 0 };
    const g = group(cfg.rows, ctx);
    const cg = cfg.cmpRows ? group(cfg.cmpRows, cctx) : null;
    let list = [...g.values()];
    const q = st.q.trim().toLowerCase();
    if (q) list = list.filter(o => { const hit = (o.l1 + ' ' + o.l2).toLowerCase().includes(q); return st.qmode === 'in' ? hit : !hit; });
    const sortKey = st.sort ? st.sort.k : (cfg.sort || metrics.find(k => !M[k].ratio) || metrics[0]);
    const dir = st.sort ? st.sort.d : (cfg.sortDir || -1);
    list.sort((a, b) => {
      if (sortKey === '_dim') { const x = a.o1 != null ? a.o1 : a.l1, y = b.o1 != null ? b.o1 : b.l1; return (x > y ? 1 : x < y ? -1 : 0) * dir; }
      const x = a.v[sortKey], y = b.v[sortKey]; return ((x == null ? -Infinity : x) - (y == null ? -Infinity : y)) * dir;
    });
    const usedRows = list.flatMap(o => o.rows);
    const tot = agg(usedRows, metrics);
    const allTot = agg(cfg.rows.filter(r => dimOf(st.dim).get(r, ctx) != null), metrics);
    const ctot = cg ? agg([...cg.values()].flatMap(o => o.rows), metrics) : null;
    const pages = Math.max(1, Math.ceil(list.length / st.n)); if (st.page >= pages) st.page = pages - 1;
    const view = list.slice(st.page * st.n, st.page * st.n + st.n);
    const d1 = dimOf(st.dim), d2 = st.dim2 ? dimOf(st.dim2) : null;
    const showMetrics = st.view === 'table' ? metrics : [st.vm];
    const arr = k => sortKey === k ? `<span class="arr">${dir < 0 ? '▼' : '▲'}</span>` : '';
    const cell = (k, v, o) => {
      let h = fmt(k, v[k]);
      if (cfg.share && k === cfg.share && tot[k]) h += `<span class="share">(${(v[k] / allTot[k] * 100).toFixed(1)}%)</span>`;
      if (cg) { const c = o ? (cg.get(o.key) || { v: {} }).v : ctot; h += `<span class="c2">${fmt(k, c[k])}</span><span class="c3">${chgHtml(k, v[k], c[k])}</span>`; }
      return h;
    };
    let head = `<tr><th class="dim${sortKey === '_dim' ? ' sorted' : ''}" data-s="_dim">${esc(d1.label)}${arr('_dim')}</th>`;
    if (d2) head += `<th class="dim">${esc(d2.label)}</th>`;
    head += showMetrics.map(k => `<th data-s="${k}" class="${sortKey === k ? 'sorted' : ''}"${tipAttr(k)}>${esc(M[k].l)}${arr(k)}</th>`).join('');
    if (st.view === 'pie') head += '<th>割合</th>';
    if (st.view === 'cmp') head += `<th>平均（${fmt(st.vm, tot[st.vm] != null && list.length ? avgOf(list, st.vm) : null)}）との差</th>`;
    head += '</tr>';
    const mixed = showMetrics.some(k => M[k].ratio || M[k].wavg || M[k].last || M[k].avg);
    const totLabel = mixed ? '<span data-tip="足し合わせられる指標は合計、フォロワー数や割合などは全体の平均（割合は全体から計算し直した値）です。" data-tip-title="合計・平均">合計・平均</span>' : '合計';
    let body = `<tr class="total"><td class="dim">${totLabel}${q ? `<span class="share">（全体の ${allTot[showMetrics[0]] ? (tot[showMetrics[0]] / allTot[showMetrics[0]] * 100).toFixed(1) : '—'}%）</span>` : ''}${cg ? '<span class="c2">比較期間</span><span class="c3 muted">変化</span>' : ''}</td>${d2 ? '<td></td>' : ''}${showMetrics.map(k => `<td>${cell(k, tot)}</td>`).join('')}${st.view === 'pie' ? '<td>100%</td>' : ''}${st.view === 'cmp' ? '<td></td>' : ''}</tr>`;
    const avg = st.view === 'cmp' ? avgOf(list, st.vm) : null;
    view.forEach((o, i) => {
      const click = cfg.onRow && cfg.rowClickable && cfg.rowClickable(st.dim);
      body += `<tr class="${click ? 'click' : ''}" data-key="${esc(o.key)}"><td class="dim"><span class="i">${st.page * st.n + i + 1}.</span>${click ? `<span class="lnk">${esc(o.l1)}</span>` : esc(o.l1)}</td>`;
      if (d2) body += `<td class="dim">${esc(o.l2)}</td>`;
      body += showMetrics.map(k => `<td>${cell(k, o.v, o)}</td>`).join('');
      if (st.view === 'pie') body += `<td>${tot[st.vm] ? (o.v[st.vm] / tot[st.vm] * 100).toFixed(1) + '%' : '—'}</td>`;
      if (st.view === 'cmp') {
        const r = avg ? (o.v[st.vm] - avg) / Math.abs(avg) : 0; const w = Math.min(50, Math.abs(r) * 50);
        const good = M[st.vm].down ? r < 0 : r > 0;
        body += `<td><div style="display:flex;align-items:center;gap:8px;justify-content:flex-end"><span class="chg ${r === 0 ? 'flat' : good ? 'up' : 'down'}">${r > 0 ? '+' : ''}${(r * 100).toFixed(1)}%</span><div class="cmpbar"><b class="${r >= 0 ? 'pos' : 'neg'}" style="width:${w}%;${good ? '' : 'background:var(--red)'}${r >= 0 && !good ? '' : ''}"></b></div></div></td>`;
      }
      body += '</tr>';
    });
    if (!view.length) body += `<tr><td class="dim muted" colspan="${showMetrics.length + 3}">表示する行がありません</td></tr>`;
    const dimBtns = cfg.dims.map(d => `<button data-d="${d.key}" class="${d.key === st.dim ? 'on' : ''}">${esc(d.label)}</button>`).join('');
    const sec = `<select class="dim2" aria-label="セカンダリ ディメンション"><option value="">セカンダリ ディメンション</option>${cfg.dims.filter(d => d.key !== st.dim).map(d => `<option value="${d.key}"${d.key === st.dim2 ? ' selected' : ''}>${esc(d.label)}</option>`).join('')}</select>`;
    const viewSel = st.view !== 'table' ? `<select class="vm" aria-label="表示する指標">${metricOptions(st.view === 'pie' ? addable : metrics, st.vm)}</select>` : '';
    el.innerHTML = `
      <div class="xbar"><div class="dims"><span class="lab">プライマリ ディメンション:</span>${dimBtns}</div></div>
      <div class="xbar2">
        ${sec}
        <div class="seg views" role="group" aria-label="表示の切り替え">
          <button data-v="table" class="${st.view === 'table' ? 'on' : ''}" title="表">表</button>
          <button data-v="pie" class="${st.view === 'pie' ? 'on' : ''}" title="割合（円グラフ）">割合</button>
          <button data-v="cmp" class="${st.view === 'cmp' ? 'on' : ''}" title="平均との比較">比較</button>
        </div>
        ${viewSel}
        <div class="search">
          <select class="qm" aria-label="検索の条件"><option value="in"${st.qmode === 'in' ? ' selected' : ''}>含む</option><option value="ex"${st.qmode === 'ex' ? ' selected' : ''}>含まない</option></select>
          <input type="search" class="q" placeholder="検索" value="${esc(st.q)}" aria-label="表の検索">
          <button class="btn small csv" title="CSV をダウンロード">CSV</button>
        </div>
      </div>
      ${st.view === 'pie' && addable.length ? `<div class="xsplit"><div class="tbl-wrap"><table class="x"><thead>${head}</thead><tbody>${body}</tbody></table></div><div class="pie"><div class="chart-wrap"><canvas></canvas></div></div></div>`
        : `<div class="tbl-wrap"><table class="x"><thead>${head}</thead><tbody>${body}</tbody></table></div>`}
      <div class="xfoot">
        <label>表示する行数: <select class="n">${[10, 25, 50, 100].map(n => `<option${n === st.n ? ' selected' : ''}>${n}</option>`).join('')}</select></label>
        <span>${list.length ? st.page * st.n + 1 : 0} 〜 ${Math.min(list.length, (st.page + 1) * st.n)} / ${list.length}行</span>
        <span class="pg"><button class="btn small prev"${st.page ? '' : ' disabled'} aria-label="前のページ">‹</button><button class="btn small next"${st.page < pages - 1 ? '' : ' disabled'} aria-label="次のページ">›</button></span>
      </div>`;
    // 円グラフ
    if (st.view === 'pie') {
      const top = list.slice().sort((a, b) => (b.v[st.vm] || 0) - (a.v[st.vm] || 0));
      const main = top.slice(0, 7), rest = top.slice(7).reduce((s, o) => s + (o.v[st.vm] || 0), 0);
      const labels = main.map(o => o.l1 + (o.l2 ? ' / ' + o.l2 : '')), data = main.map(o => o.v[st.vm] || 0);
      if (rest > 0) { labels.push('その他'); data.push(rest); }
      const cv = $('.pie canvas', el);
      if (cv) mkChart(cv, { type: 'doughnut', data: { labels, datasets: [{ data, backgroundColor: SERIES_COLORS, borderWidth: 1 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 11 } } },
          tooltip: { callbacks: { label: it => ` ${it.label}: ${fmt(st.vm, it.raw)}（${(it.raw / data.reduce((a, b) => a + b, 0) * 100).toFixed(1)}%）` } } } } }, 'x-' + cfg.id);
    }
    // 操作
    $$('.dims button', el).forEach(b => { b.onclick = () => { if (b.dataset.d === st.dim) return; st.dim = b.dataset.d; if (st.dim2 === st.dim) st.dim2 = ''; st.page = 0; st.sort = null; draw(); }; });
    $('.dim2', el).onchange = e => { st.dim2 = e.target.value; st.page = 0; draw(); };
    $$('.views button', el).forEach(b => { b.onclick = () => { st.view = b.dataset.v; if (st.view === 'pie' && !addable.includes(st.vm)) st.vm = addable[0]; draw(); }; });
    if ($('.vm', el)) $('.vm', el).onchange = e => { st.vm = e.target.value; draw(); };
    $$('th[data-s]', el).forEach(th => { th.onclick = () => { const k = th.dataset.s; st.sort = { k, d: st.sort && st.sort.k === k ? -st.sort.d : (k === '_dim' ? 1 : -1) }; draw(); }; });
    const qi = $('.q', el); let timer;
    qi.oninput = () => { clearTimeout(timer); timer = setTimeout(() => { st.q = qi.value; st.page = 0; draw(); const n = $('.q', el); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 250); };
    $('.qm', el).onchange = e => { st.qmode = e.target.value; st.page = 0; draw(); };
    $('.n', el).onchange = e => { st.n = +e.target.value; st.page = 0; draw(); };
    $('.prev', el).onclick = () => { st.page--; draw(); };
    $('.next', el).onclick = () => { st.page++; draw(); };
    $('.csv', el).onclick = () => downloadCsv(cfg, list, d1, d2, cg);
    if (cfg.onRow && cfg.rowClickable && cfg.rowClickable(st.dim)) $$('tr.click', el).forEach(tr => { tr.onclick = () => { const o = g.get(tr.dataset.key); if (o) cfg.onRow(o.ref); }; });
  }
  draw();
}
function avgOf(list, k) { const v = list.map(o => o.v[k]).filter(x => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }
function csvVal(k, v) { if (v == null) return ''; const f = M[k].f; if (f === 'pct') return (v * 100).toFixed(2); if (f === 'pct1' || f === 'sec' || f === 'dec1') return v.toFixed(1); return Math.round(v); }
function downloadCsv(cfg, list, d1, d2, cg) {
  const q = s => '"' + String(s).replace(/"/g, '""') + '"';
  const unit = k => { const f = M[k].f; return f === 'pct' || f === 'pct1' ? '（%）' : f === 'sec' ? '（秒）' : ''; };
  const head = [d1.label]; if (d2) head.push(d2.label);
  cfg.metrics.forEach(k => { head.push(M[k].l + unit(k)); if (cg) head.push(M[k].l + unit(k) + '・比較期間'); });
  const lines = [head.map(q).join(',')];
  for (const o of list) {
    const row = [o.l1]; if (d2) row.push(o.l2);
    const c = cg ? (cg.get(o.key) || { v: {} }).v : null;
    cfg.metrics.forEach(k => { row.push(csvVal(k, o.v[k])); if (cg) row.push(csvVal(k, c[k])); });
    lines.push(row.map(q).join(','));
  }
  const meta = [`# 期間: ${ymd(S.eff.cur[0])}〜${ymd(S.eff.cur[1])}` + (cg && S.eff.cmp ? ` / 比較期間: ${ymd(S.eff.cmp[0])}〜${ymd(S.eff.cmp[1])}` : ''), `# アカウント: ${curD().acc.name}`];
  const blob = new Blob(['﻿' + meta.join('\r\n') + '\r\n' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = `instagram_${S.report}_${ds(S.range[0])}_${ds(S.range[1])}.csv`;
  document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  toast('CSV をダウンロードしました');
}

/* ディメンションの定義 */
const dateDims = [
  { key: 'date', label: '日付', get: (r, c) => ({ k: r._d - c.start, l: ymd(r._d) + '（' + WD[wdOf(r._d)] + '）', o: r._d - c.start }) },
  { key: 'week', label: '週', get: (r, c) => { const ws = r._d - wdOf(r._d); return { k: Math.floor((ws - (c.start - wdOf(c.start))) / 7), l: ymd(Math.max(ws, c.start)) + ' からの週', o: ws }; } },
  { key: 'month', label: '月', get: (r, c) => { const m = monthOf(r._d); const sm = monthOf(c.start); return { k: (+m.slice(0, 4) * 12 + +m.slice(5)) - (+sm.slice(0, 4) * 12 + +sm.slice(5)), l: m.replace('-', '年') + '月', o: m }; } },
  { key: 'wd', label: '曜日', get: r => ({ k: wdOf(r._d), l: WD[wdOf(r._d)] + '曜日', o: wdOf(r._d) }) },
];
const BANDS = [[0, 6, '0〜5時'], [6, 9, '6〜8時'], [9, 12, '9〜11時'], [12, 15, '12〜14時'], [15, 18, '15〜17時'], [18, 21, '18〜20時'], [21, 24, '21〜23時']];
const bandOf = h => BANDS.findIndex(b => h >= b[0] && h < b[1]);
const postDims = [
  { key: 'post', label: '投稿', get: r => ({ k: r._p.id, l: r._p.title || r._p.caption_head || r._p.id }) },
  { key: 'format', label: '形式', get: r => ({ k: r._p.format, l: r._p.format || '不明' }) },
  { key: 'topic', label: '話題', get: r => ({ k: r._p.topic || '', l: r._p.topic || '（分類なし）' }) },
  { key: 'style', label: 'リールの型', get: r => r._p.format === 'リール' ? ({ k: r._p.reel_style || '', l: STYLE_NAME[r._p.reel_style] || '（型の記録なし）' }) : null },
  { key: 'wd', label: '投稿した曜日', get: r => ({ k: wdOf(r._p._d), l: WD[wdOf(r._p._d)] + '曜日', o: wdOf(r._p._d) }) },
  { key: 'hour', label: '投稿した時間帯', get: r => r._p._h == null ? null : ({ k: bandOf(r._p._h), l: BANDS[bandOf(r._p._h)][2], o: bandOf(r._p._h) }) },
  { key: 'pdate', label: '投稿日', get: r => ({ k: r._p.date, l: ymd(r._p._d), o: r._p._d }) },
];

/* ================= 画面 ================= */
function renderNav() {
  const side = $('#side');
  side.innerHTML = NAV.map(n => {
    const ic = p => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${p}" fill="currentColor"/></svg>`;
    if (n.sep) return '<div class="nav-sep"></div>';
    if (n.id) return `<a class="nav-item" href="#${n.id}" data-r="${n.id}">${ic(n.icon)}<span>${esc(n.label)}</span>${n.soon ? '<span class="soon">準備中</span>' : ''}</a>`;
    return `<div class="nav-group" data-g="${esc(n.group)}"><button aria-expanded="false">${ic(n.icon)}<span>${esc(n.group)}</span><span class="caret">▶</span></button><div class="nav-sub">${n.items.map(([id, l]) => `<a class="nav-item" href="#${id}" data-r="${id}">${esc(l)}</a>`).join('')}</div></div>`;
  }).join('');
  $$('.nav-group > button', side).forEach(b => { b.onclick = () => { const g = b.parentNode; g.classList.toggle('open'); b.setAttribute('aria-expanded', g.classList.contains('open')); }; });
  $$('.nav-item', side).forEach(a => { a.addEventListener('click', () => document.body.classList.remove('nav-open')); });
}
function markNav() {
  $$('.nav-item').forEach(a => a.classList.toggle('active', a.dataset.r === S.report));
  const info = navInfo(S.report);
  $$('.nav-group').forEach(g => { if (info && g.dataset.g === info.group) { g.classList.add('open'); $('button', g).setAttribute('aria-expanded', 'true'); } });
}

let renderSeq = 0;
async function render() {
  const seq = ++renderSeq;
  closeModal();
  const info = navInfo(S.report) || navInfo('home');
  $('#crumb').textContent = info.group;
  $('#title').textContent = info.label;
  document.title = info.label + ' | Instagram 分析';
  markNav();
  destroyCharts();
  const body = $('#body'), notice = $('#notice');
  notice.innerHTML = '';
  const D = curD();
  $('#dr').hidden = S.report === 'realtime' || S.report === 'review';
  try {
    if (S.report === 'realtime') { body.innerHTML = '<div class="empty">読み込み中…</div>'; await ensureMonths(D, D.acc.post_daily_months || []); if (seq !== renderSeq) return; body.innerHTML = ''; return renderRealtime(D, body); }
    if (S.report === 'review') return renderReview(D, body);
    await ensureMonths(D, neededMonths(D));
    if (seq !== renderSeq) return;
  } catch (e) {
    body.innerHTML = `<div class="empty"><strong>データを読み込めませんでした</strong>${esc(e.message)}</div>`; return;
  }
  const cur = clip(D, S.range[0], S.range[1]);
  if (!cur) { body.innerHTML = emptyMsg(D); return; }
  const notes = [];
  if (cur[0] !== S.range[0] || cur[1] !== S.range[1]) notes.push(`選んだ期間のうち、記録があるのは ${mdj(cur[0])}〜${mdj(cur[1])} です（記録開始: ${mdj(D.recStart)}、最新の記録: ${mdj(D.last)}）。`);
  let cmp = null;
  if (S.cmp.on) {
    let cs = S.cmp.start, ce = S.cmp.end;
    // 選んだ期間の一部しか記録がないときは、比較期間も同じ日にちの分だけにそろえる
    if (ce - cs === S.range[1] - S.range[0]) { cs += cur[0] - S.range[0]; ce -= S.range[1] - cur[1]; }
    cmp = clip(D, cs, ce); if (!cmp) notes.push(`比較期間（${ymd(S.cmp.start)}〜${ymd(S.cmp.end)}）はまだ記録がないため、比較は出せません（記録開始: ${mdj(D.recStart)}）。`); else if (cmp[0] !== cs || cmp[1] !== ce) notes.push(`比較期間のうち、記録があるのは ${mdj(cmp[0])}〜${mdj(cmp[1])} だけです。`);
    else if (cs !== S.cmp.start || ce !== S.cmp.end) notes.push(`比較期間も、記録がある日数にそろえて ${mdj(cs)}〜${mdj(ce)} で比べています。`); }
  if (D.acc.sample) notes.push('いま表示しているのは試作用のサンプルデータです（本物の数字ではありません）。');
  notice.innerHTML = notes.map((n, i) => `<div class="note${i === notes.length - 1 && D.acc.sample ? ' info' : ''}">${esc(n)}</div>`).join('');
  const ctx = { D, cur, cmp }; S.eff = { cur, cmp };
  const fn = {
    home: renderHome, 'aud-overview': renderAudOverview, 'aud-followers': renderAudFollowers, 'aud-demo': renderDemo, 'aud-geo': renderGeo, 'aud-online': renderOnline,
    'content-all': (c, b) => renderContent(c, b, 'post'), 'content-format': (c, b) => renderContent(c, b, 'format'), 'content-topic': (c, b) => renderContent(c, b, 'topic'),
    'content-style': (c, b) => renderContent(c, b, 'style'), 'content-time': (c, b) => renderContent(c, b, 'wd'),
    'comp-overview': renderCompOverview, 'comp-trend': renderCompTrend, 'comp-posts': renderCompPosts,
  }[S.report] || renderHome;
  body.innerHTML = '';
  fn(ctx, body);
}
function emptyMsg(D, what) {
  return `<div class="empty"><strong>この期間はまだ記録がありません（記録開始: ${mdj(D.recStart)}）</strong>${what ? esc(what) + '<br>' : ''}最新の記録は ${mdj(D.last)} です。記録は毎晩、前日の分までを追加します。右上で期間を変えてください。</div>`;
}
function card(parent, title, opts = {}) {
  const c = document.createElement('section'); c.className = 'card';
  c.innerHTML = (title ? `<div class="card-h"><h2>${title}</h2><div class="right"></div></div>` : '') + '<div class="cb"></div>' + (opts.foot ? `<div class="card-f">${opts.foot}</div>` : '');
  parent.appendChild(c); return { el: c, body: $('.cb', c), right: $('.right', c) };
}

/* ---- 共通: グラフ＋スコアカード＋表 のレポート ---- */
function standardReport(parent, o) {
  const top = card(parent, null);
  const chartEl = document.createElement('div'); top.body.appendChild(chartEl);
  const scoreEl = document.createElement('div'); scoreEl.className = 'scores'; top.body.appendChild(scoreEl);
  const tc = trendChart(chartEl, { id: o.id, metrics: o.chartMetrics, m1: o.m1, m2: o.m2, days: o.days, cmpDays: o.cmpDays, onMetric: k => scorecards(scoreEl, sc) });
  const sc = { keys: o.scoreKeys, days: o.days, cmpDays: o.cmpDays, selected: () => S.ch[o.id].m1, onPick: k => { if (o.chartMetrics.includes(k)) tc.setMetric(k); } };
  scorecards(scoreEl, sc);
  if (o.extra) o.extra(parent);
  if (o.table) { const t = card(parent, null); explorer(t.body, o.table); }
}

/* ---- ホーム ---- */
function renderHome({ D, cur, cmp }, body) {
  const days = accountDays(D, cur[0], cur[1]), cdays = cmp ? accountDays(D, cmp[0], cmp[1]) : null;
  const rows = contentRows(D, cur[0], cur[1]);
  const keys = ['reach', 'views', 'total_interactions', 'net_follows', 'followers'];
  const A = agg(days, keys), B = cdays ? agg(cdays, keys) : null;
  const g = document.createElement('div'); g.className = 'grid2'; body.appendChild(g);
  const c1 = card(g, 'アカウントの概要', { foot: '<a href="#aud-overview">オーディエンスの概要を見る ›</a>' });
  c1.body.innerHTML = `<div class="kpis">${keys.map(k => `<button class="kpi${k === S.home.kpi ? ' on' : ''}" data-k="${k}"><div class="lab"${tipAttr(k)}>${esc(M[k].l)}</div><div class="val">${fmt(k, A[k])}</div>${B ? chgHtml(k, A[k], B[k]) : ''}</button>`).join('')}</div><div class="legend"></div><div class="chart-wrap short"><canvas></canvas></div>`;
  const drawK = () => {
    destroyCharts('home-k'); const k = S.home.kpi;
    const dsets = [{ label: '選んだ期間', data: days.map(d => d[k]), borderColor: C1, backgroundColor: 'rgba(30,111,217,.10)', fill: true, borderWidth: 2, pointRadius: 0, tension: .15 }];
    if (cdays) dsets.push({ label: '比較期間', data: days.map((_, i) => cdays[i] ? cdays[i][k] : null), borderColor: C1, borderDash: [5, 4], borderWidth: 1.5, pointRadius: 0, fill: false, tension: .15 });
    $('.legend', c1.body).innerHTML = `<span><i style="border-color:${C1}"></i>${esc(M[k].l)}（${mdj(cur[0])}〜${mdj(cur[1])}）</span>` + (cdays ? `<span><i class="dash" style="border-color:${C1}"></i>比較期間（${mdj(cmp[0])}〜${mdj(cmp[1])}）</span>` : '');
    mkChart($('canvas', c1.body), { type: 'line', data: { labels: days.map(d => mds(d._d)), datasets: dsets }, options: {
      responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.dataset.label}${it.datasetIndex && cdays[it.dataIndex] ? '（' + mds(cdays[it.dataIndex]._d) + '）' : ''}: ${fmt(k, it.raw)}` } } },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 7, maxRotation: 0, font: { size: 11 } } }, y: { beginAtZero: !M[k].last, grid: { color: '#eee' }, ticks: { maxTicksLimit: 4, font: { size: 11 }, callback: axisFmt(k) } } } } }, 'home-k');
  };
  $$('.kpi', c1.body).forEach(b => { b.onclick = () => { S.home.kpi = b.dataset.k; $$('.kpi', c1.body).forEach(x => x.classList.toggle('on', x === b)); drawK(); }; });
  drawK();
  // 直近の投稿
  const c2 = card(g, 'いちばん新しい投稿', { foot: '<a href="#realtime">リアルタイムを見る ›</a>' });
  const lp = D.posts[D.posts.length - 1];
  if (lp) {
    const t = postDelta(D, lp, lp._d, D.last);
    c2.body.innerHTML = `<div class="card-b"><div class="muted small">${ymd(lp._d)} ${esc(lp.time || '')}・${esc(lp.format)}</div><div style="font-weight:500;margin:4px 0 10px">${esc(lp.title)}</div>
      <div class="muted small"${tipAttr('reach')}>リーチ（${mdj(D.last)}までの累計）</div><div class="big">${fmt('reach', t.reach)}</div>
      <ul class="list small">${['views', 'likes', 'saves', 'shares'].map(k => `<li><span${tipAttr(k)}>${esc(M[k].l)}</span><span>${fmt(k, t[k])}</span></li>`).join('')}</ul></div>`;
  } else c2.body.innerHTML = '<div class="card-b muted">まだ投稿の記録がありません</div>';
  // 下の段
  const g3 = document.createElement('div'); g3.className = 'grid3'; body.appendChild(g3);
  const c3 = card(g3, 'よく見られた投稿（リーチ順）', { foot: '<a href="#content-all">すべての投稿を見る ›</a>' });
  const top = rows.slice().sort((a, b) => b.reach - a.reach).slice(0, 6);
  c3.body.innerHTML = `<div class="tbl-wrap"><table class="x"><thead><tr><th class="dim">投稿</th><th${tipAttr('reach')}>リーチ</th><th${tipAttr('eng_rate')}>反応率</th></tr></thead><tbody>${top.map((r, i) => `<tr class="click" data-i="${i}"><td class="dim"><span class="lnk">${esc(r._p.title)}</span></td><td>${fmt('reach', r.reach)}</td><td>${fmt('eng_rate', r.reach ? r.interactions / r.reach : null)}</td></tr>`).join('') || '<tr><td class="dim muted" colspan="3">この期間に見られた投稿はありません</td></tr>'}</tbody></table></div>`;
  $$('tr.click', c3.body).forEach(tr => { tr.onclick = () => openPost(top[+tr.dataset.i]._p); });
  const c4 = card(g3, '形式ごとのリーチの割合', { foot: '<a href="#content-format">形式別を見る ›</a>' });
  const byF = {}; rows.forEach(r => { byF[r._p.format] = (byF[r._p.format] || 0) + r.reach; });
  c4.body.innerHTML = '<div class="chart-wrap short"><canvas></canvas></div>';
  mkChart($('canvas', c4.body), { type: 'doughnut', data: { labels: Object.keys(byF), datasets: [{ data: Object.values(byF), backgroundColor: SERIES_COLORS, borderWidth: 1 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { position: 'right', labels: { boxWidth: 10, font: { size: 11 } } }, tooltip: { callbacks: { label: it => ` ${it.label}: ${fmt('reach', it.raw)}` } } } } });
  const c5 = card(g3, 'フォロワーがよく見ている時間帯', { foot: '<a href="#aud-online">オンラインの時間帯を見る ›</a>' });
  const snap = audSnap(D, cur[1]);
  c5.body.innerHTML = snap && snap.online_hours ? `<div class="card-b heat-wrap">${heatTable(snap.online_hours, false, v => fmt('count', v) + '人')}</div>` : '<div class="card-b muted">まだ記録がありません</div>';
}

/* ---- オーディエンス ---- */
function renderAudOverview({ D, cur, cmp }, body) {
  const days = accountDays(D, cur[0], cur[1]), cdays = cmp ? accountDays(D, cmp[0], cmp[1]) : null;
  standardReport(body, { id: 'aud', chartMetrics: ACC_METRICS, m1: 'reach', days, cmpDays: cdays,
    scoreKeys: ['reach', 'views', 'profile_views', 'website_clicks', 'accounts_engaged', 'total_interactions', 'acc_eng_rate', 'followers'],
    table: { id: 'aud', dims: dateDims, metrics: ['reach', 'views', 'profile_views', 'website_clicks', 'accounts_engaged', 'total_interactions', 'acc_eng_rate', 'net_follows'], rows: days, cmpRows: cdays, sort: '_dim', sortDir: 1 } });
}
function renderAudFollowers({ D, cur, cmp }, body) {
  const days = accountDays(D, cur[0], cur[1]), cdays = cmp ? accountDays(D, cmp[0], cmp[1]) : null;
  standardReport(body, { id: 'fol', chartMetrics: ['followers', 'follows_new', 'unfollows', 'net_follows'], m1: 'followers', m2: 'net_follows', days, cmpDays: cdays,
    scoreKeys: ['followers', 'follows_new', 'unfollows', 'net_follows'],
    table: { id: 'fol', dims: dateDims, metrics: ['followers', 'follows_new', 'unfollows', 'net_follows'], rows: days, cmpRows: cdays, sort: '_dim', sortDir: 1 } });
}
function audSnap(D, end) { let s = null; for (const x of D.aud) if (x._d <= end) s = x; return s; }
function renderDemo({ D, cur, cmp }, body) {
  const snap = audSnap(D, cur[1]);
  if (!snap || !snap.gender_age || !snap.gender_age.length) { body.innerHTML = emptyMsg(D, 'フォロワーの性別・年代の記録がありません（フォロワーが少ないと Instagram が数字を出さないことがあります）。'); return; }
  const csnap = cmp ? audSnap(D, cmp[1]) : null;
  $('#notice').insertAdjacentHTML('afterbegin', `<div class="note info">性別・年代は ${mdj(snap._d)} 時点の記録です${csnap && csnap !== snap ? `（比較: ${mdj(csnap._d)} 時点）` : ''}。</div>`);
  const ga = snap.gender_age;
  const ages = [...new Set(ga.map(x => x.age))];
  const tot = ga.reduce((s, x) => s + x.count, 0);
  const share = g => ga.filter(x => x.gender === g).reduce((s, x) => s + x.count, 0) / (tot || 1);
  const byAge = ages.map(a => ga.filter(x => x.age === a).reduce((s, x) => s + x.count, 0));
  const topAge = ages[byAge.indexOf(Math.max(...byAge))];
  const c = card(body, '年代と性別');
  c.body.innerHTML = `<div class="chart-wrap tall"><canvas></canvas></div><div class="scores">
    <div class="score"><div class="lab">女性の割合</div><div class="val">${(share('F') * 100).toFixed(1)}%</div></div>
    <div class="score"><div class="lab">男性の割合</div><div class="val">${(share('M') * 100).toFixed(1)}%</div></div>
    <div class="score"><div class="lab">いちばん多い年代</div><div class="val">${esc(topAge)}歳</div></div>
    <div class="score"><div class="lab"${tipAttr('count')}>属性がわかるフォロワー</div><div class="val">${fmt('count', tot)}</div></div></div>`;
  mkChart($('canvas', c.body), { type: 'bar', data: { labels: ages.map(a => a + '歳'), datasets: [
    { label: '女性', data: ages.map(a => (ga.find(x => x.age === a && x.gender === 'F') || {}).count || 0), backgroundColor: C1 },
    { label: '男性', data: ages.map(a => (ga.find(x => x.age === a && x.gender === 'M') || {}).count || 0), backgroundColor: C2 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10 } } }, scales: { x: { grid: { display: false } }, y: { grid: { color: '#eee' }, ticks: { maxTicksLimit: 5 } } } } });
  const toRows = s => s.gender_age.map(x => ({ age: x.age, gender: x.gender, count: x.count, _d: s._d }));
  const t = card(body, null);
  explorer(t.body, { id: 'demo', dims: [
    { key: 'age', label: '年代', get: r => ({ k: r.age, l: r.age + '歳', o: ages.indexOf(r.age) }) },
    { key: 'gender', label: '性別', get: r => ({ k: r.gender, l: GENDER[r.gender] || r.gender }) }],
    metrics: ['count'], share: 'count', rows: toRows(snap), cmpRows: csnap && csnap !== snap ? toRows(csnap) : null, sort: '_dim', sortDir: 1 });
}
function renderGeo({ D, cur, cmp }, body) {
  const snap = audSnap(D, cur[1]);
  if (!snap) { body.innerHTML = emptyMsg(D, '地域の記録がありません。'); return; }
  const csnap = cmp ? audSnap(D, cmp[1]) : null;
  $('#notice').insertAdjacentHTML('afterbegin', `<div class="note info">地域は ${mdj(snap._d)} 時点の記録です。</div>`);
  const toRows = s => [].concat(
    (s.cities || []).map(x => ({ kind: 'city', name: x.name, count: x.count })),
    (s.regions || []).map(x => ({ kind: 'region', name: x.name, count: x.count })),
    (s.countries || []).map(x => ({ kind: 'country', name: x.name, count: x.count })));
  const mk = kind => r => r.kind === kind ? { k: r.name, l: r.name } : null;
  const t = card(body, null);
  if (!S.tb.geo) S.tb.geo = { dim: 'region', dim2: '', sort: null, q: '', qmode: 'in', n: 10, page: 0, view: 'pie', vm: 'count' };
  explorer(t.body, { id: 'geo', dims: [{ key: 'region', label: '都道府県', get: mk('region') }, { key: 'city', label: '市区町村', get: mk('city') }, { key: 'country', label: '国', get: mk('country') }],
    metrics: ['count'], share: 'count', rows: toRows(snap), cmpRows: csnap && csnap !== snap ? toRows(csnap) : null });
}
function heatTable(grid, big, title) {
  const mx = Math.max(1, ...grid.flat());
  const hrs = [...Array(24).keys()];
  return `<table class="heat${big ? ' big' : ''}"><thead><tr><th></th>${hrs.map(h => `<th>${big || h % 3 === 0 ? h : ''}</th>`).join('')}</tr></thead><tbody>${grid.map((row, w) => `<tr><th>${WD[w]}</th>${row.map((v, h) => { const a = v / mx; return `<td class="v" title="${WD[w]}曜 ${h}時: ${esc(title(v))}" style="background:rgba(30,111,217,${(0.06 + a * 0.9).toFixed(2)});${a > 0.55 ? 'color:#fff' : ''}">${big ? Math.round(v) : ''}</td>`; }).join('')}</tr>`).join('')}</tbody></table>`;
}
function renderOnline({ D, cur }, body) {
  const snap = audSnap(D, cur[1]);
  if (!snap || !snap.online_hours) { body.innerHTML = emptyMsg(D, 'オンラインの時間帯の記録がありません。'); return; }
  $('#notice').insertAdjacentHTML('afterbegin', `<div class="note info">${mdj(snap._d)} 時点の記録です。色が濃いほど、その曜日・時刻に Instagram を開いているフォロワーが多いことを表します。</div>`);
  const grid = snap.online_hours;
  const c = card(body, '曜日 × 時刻（オンラインのフォロワーの数）');
  c.body.innerHTML = `<div class="card-b heat-wrap">${heatTable(grid, true, v => v + '人')}</div>`;
  const flat = []; grid.forEach((r, w) => r.forEach((v, h) => flat.push({ w, h, v })));
  const best = flat.sort((a, b) => b.v - a.v).slice(0, 5);
  const c2 = card(body, '時刻ごとの平均');
  c2.body.innerHTML = `<div class="chart-wrap short"><canvas></canvas></div><div class="card-b"><div class="muted small" style="margin-bottom:4px">フォロワーがいちばん多い時間（投稿の時刻の目安）</div><ul class="list">${best.map(b => `<li><span>${WD[b.w]}曜日 ${b.h}時台</span><span>${b.v}人</span></li>`).join('')}</ul></div>`;
  mkChart($('canvas', c2.body), { type: 'bar', data: { labels: [...Array(24).keys()].map(h => h + '時'), datasets: [{ label: '平均', data: [...Array(24).keys()].map(h => grid.reduce((s, r) => s + r[h], 0) / 7), backgroundColor: C1 }] },
    options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` 平均 ${Math.round(it.raw)}人` } } }, scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, font: { size: 10 } } }, y: { grid: { color: '#eee' }, ticks: { maxTicksLimit: 4 } } } } });
  const rows = []; grid.forEach((r, w) => r.forEach((v, h) => rows.push({ w, h, online: v })));
  const t = card(body, null);
  explorer(t.body, { id: 'online', dims: [{ key: 'w', label: '曜日', get: r => ({ k: r.w, l: WD[r.w] + '曜日', o: r.w }) }, { key: 'h', label: '時刻', get: r => ({ k: r.h, l: r.h + '時台', o: r.h }) }],
    metrics: ['online'], rows, sort: 'online' });
}

/* ---- コンテンツ ---- */
function renderContent({ D, cur, cmp }, body, dim) {
  const rows = contentRows(D, cur[0], cur[1]), crows = cmp ? contentRows(D, cmp[0], cmp[1]) : null;
  const filt = S.report === 'content-style' ? (p => p.format === 'リール') : null;
  const days = contentDays(D, cur[0], cur[1], filt), cdays = cmp ? contentDays(D, cmp[0], cmp[1], filt) : null;
  if (filt) $('#notice').insertAdjacentHTML('beforeend', '<div class="note info">このページのグラフと合計はリールだけを数えています。</div>');
  const id = 'content-' + dim;
  if (!S.tb[id]) S.tb[id] = { dim, dim2: '', sort: null, q: '', qmode: 'in', n: dim === 'post' ? 10 : 25, page: 0, view: 'table', vm: null };
  standardReport(body, { id: 'content', chartMetrics: CONTENT_METRICS, m1: 'reach', days, cmpDays: cdays,
    scoreKeys: filt ? ['posts', 'reach', 'views', 'interactions', 'eng_rate', 'avg_watch', 'skip_rate', 'follows'] : ['posts', 'reach', 'views', 'interactions', 'eng_rate', 'saves', 'shares', 'follows'],
    extra: S.report === 'content-time' ? p => timeHeat(p, rows) : null,
    table: { id, dim, dims: postDims, metrics: CONTENT_TABLE, rows: filt ? rows.filter(r => filt(r._p)) : rows, cmpRows: crows ? (filt ? crows.filter(r => filt(r._p)) : crows) : null, sort: 'reach',
      onRow: r => openPost(r._p), rowClickable: d => d === 'post' } });
}
function timeHeat(parent, rows) {
  const c = card(parent, '曜日 × 時間帯（期間内に投稿した投稿1本あたりの平均リーチ）');
  const posted = rows.filter(r => r.posts && r._p._h != null);
  const sum = WD.map(() => BANDS.map(() => [0, 0]));
  posted.forEach(r => { const s = sum[wdOf(r._p._d)][bandOf(r._p._h)]; s[0] += r.reach; s[1]++; });
  const vals = sum.flat().filter(x => x[1]).map(x => x[0] / x[1]); const mx = Math.max(1, ...vals);
  c.body.innerHTML = `<div class="card-b heat-wrap"><table class="heat big"><thead><tr><th></th>${BANDS.map(b => `<th>${b[2]}</th>`).join('')}</tr></thead><tbody>${sum.map((row, w) => `<tr><th>${WD[w]}</th>${row.map(([s, n]) => { if (!n) return '<td style="background:#f8f9fa;color:#bbb" title="投稿なし">-</td>'; const v = s / n, a = v / mx; return `<td class="v" title="${n}本の平均" style="background:rgba(30,111,217,${(0.08 + a * 0.85).toFixed(2)});${a > 0.55 ? 'color:#fff' : ''}">${Math.round(v).toLocaleString('ja-JP')}<br><span style="font-size:10px;opacity:.8">${n}本</span></td>`; }).join('')}</tr>`).join('')}</tbody></table>
  <div class="muted small" style="margin-top:6px">投稿した日の曜日と時刻で分けています。本数が少ないマスは偶然の差が大きいので、目安として見てください。</div></div>`;
}

/* ---- 投稿の詳細 ---- */
async function openPost(p) {
  const D = curD();
  const m = $('#modal'); m.hidden = false; m.innerHTML = '<div class="dlg"><div class="dlg-h"><h2>読み込み中</h2></div></div>';
  await ensureMonths(D, D.acc.post_daily_months || []);
  const end = D.last;
  const total = postRow(D, p, Math.max(p._d, 0), end);
  const inR = clip(D, S.range[0], S.range[1]);
  const period = inR ? postRow(D, p, inR[0], inR[1]) : null;
  const keys = ['reach', 'views', 'interactions', 'eng_rate', 'likes', 'comments', 'saves', 'shares', 'follows', 'profile_visits'].concat(p.format === 'リール' ? ['avg_watch', 'skip_rate'] : []);
  const tv = agg([total], keys), pv = period ? agg([period], keys) : null;
  const link = p.permalink ? `<a href="${esc(p.permalink)}" target="_blank" rel="noopener">Instagram で見る ↗</a>` : '<span class="muted small">（サンプルのため Instagram へのリンクはありません）</span>';
  m.innerHTML = `<div class="dlg" role="dialog" aria-modal="true" aria-label="投稿の詳細">
    <div class="dlg-h"><div class="thumb">${p.thumbnail_url ? `<img src="${esc(p.thumbnail_url)}" alt="">` : esc(p.format)}</div>
      <div><h2>${esc(p.title)}</h2><div class="muted small">${ymd(p._d)} ${esc(p.time || '')}・${esc(p.format)}${p.reel_style ? '・' + esc(STYLE_NAME[p.reel_style] || p.reel_style) : ''}・話題: ${esc(p.topic || '—')}</div>
      <div class="small" style="margin:6px 0">${esc(p.caption_head || '')}</div>${link}</div>
      <button class="x" aria-label="閉じる">×</button></div>
    <div class="card-h"><h2>${mdj(end)}までの累計</h2></div>
    <div class="scores">${keys.map(k => `<div class="score"><div class="lab"${tipAttr(k)}>${esc(M[k].l)}</div><div class="val">${fmt(k, tv[k])}</div>${pv ? `<div class="muted small">選んだ期間: ${fmt(k, pv[k])}</div>` : ''}</div>`).join('')}</div>
    <div class="ctrl" style="padding-bottom:4px"><select class="pm" aria-label="指標">${metricOptions(keys.filter(k => !M[k].ratio && !M[k].wavg), 'reach')}</select>
      <div class="seg" role="group" aria-label="グラフの種類"><button data-m="cum" class="on">累計</button><button data-m="day">日ごと</button></div></div>
    <div class="chart-wrap"><canvas></canvas></div></div>`;
  let mode = 'cum';
  const draw = () => {
    destroyCharts('post'); const k = $('.pm', m).value;
    const xs = []; for (let x = Math.max(p._d, D.recStart); x <= end; x++) xs.push(x);
    const data = xs.map(x => { const r = postRow(D, p, mode === 'cum' ? Math.max(p._d, D.recStart) : x, x); return k === 'interactions' ? r.interactions : r[k]; });
    mkChart($('canvas', m), { type: mode === 'cum' ? 'line' : 'bar', data: { labels: xs.map(x => mds(x)), datasets: [{ label: M[k].l, data, borderColor: C1, backgroundColor: mode === 'cum' ? 'rgba(30,111,217,.10)' : C1, fill: true, pointRadius: 0, tension: .15, borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, maxRotation: 0 } }, y: { beginAtZero: true, grid: { color: '#eee' }, ticks: { maxTicksLimit: 5 } } } } }, 'post');
  };
  $('.pm', m).onchange = draw;
  $$('.seg button', m).forEach(b => { b.onclick = () => { mode = b.dataset.m; $$('.seg button', m).forEach(x => x.classList.toggle('on', x === b)); draw(); }; });
  $('.x', m).onclick = closeModal;
  m.onclick = e => { if (e.target === m) closeModal(); };
  draw();
}
function closeModal() { const m = $('#modal'); if (!m.hidden) { destroyCharts('post'); m.hidden = true; m.innerHTML = ''; } }

/* ---- リアルタイム（直近の投稿） ---- */
function renderRealtime(D, body) {
  $('#notice').innerHTML = `<div class="note info">いちばん新しい投稿を、記録した日ごとに追いかけます（最新の記録: ${mdj(D.last)}。毎晩、前日の分まで追加）。このページは右上の期間に関係なく表示します。${D.acc.sample ? '数字はサンプルです。' : ''}</div>`;
  const latest = D.posts.slice(-6).reverse();
  if (!latest.length) { body.innerHTML = '<div class="empty"><strong>まだ投稿の記録がありません</strong></div>'; return; }
  const median = arr => { const a = arr.slice().sort((x, y) => x - y); return a.length ? a[Math.floor(a.length / 2)] : null; };
  const wrap = document.createElement('div'); wrap.className = 'posts-rt'; body.appendChild(wrap);
  latest.forEach(p => {
    const age = D.last - p._d + 1;
    const t = postRow(D, p, p._d, D.last);
    const peers = D.posts.filter(q => q !== p && q.format === p.format && D.last - q._d + 1 > age).map(q => postRow(D, q, q._d, q._d + age - 1).reach);
    const med = median(peers);
    const ratio = med ? t.reach / med : null;
    const incs = []; for (let x = p._d; x <= Math.min(D.last, p._d + 13); x++) incs.push(postRow(D, p, x, x).reach);
    const c = document.createElement('section'); c.className = 'card rt';
    c.innerHTML = `<div class="card-b"><div class="thumb">${p.thumbnail_url ? `<img src="${esc(p.thumbnail_url)}" alt="">` : esc(p.format)}</div><div style="min-width:0;flex:1">
      <h3>${esc(p.title)}</h3><div class="meta">${ymd(p._d)} ${esc(p.time || '')}・投稿から${age}日目</div>
      <div style="margin-top:6px">${ratio == null ? '<span class="pill">比べる投稿がまだありません</span>' : `<span class="pill ${ratio >= 1 ? 'good' : 'bad'}" data-tip="同じ形式の過去の投稿が、投稿から${age}日目までに届いたリーチの中央値（${fmt('reach', med)}）と比べています。" data-tip-title="いつもと比べて">いつもの ${(ratio * 100).toFixed(0)}%</span>`}</div></div></div>
      <div class="rt-stats">${['reach', 'views', 'interactions'].map(k => `<div><div class="lab"${tipAttr(k)}>${esc(M[k].l)}</div><div class="val">${fmt(k, t[k])}</div></div>`).join('')}</div>
      <div class="chart-wrap short" style="height:110px"><canvas></canvas></div>`;
    wrap.appendChild(c);
    c.querySelector('.card-b').style.cursor = 'pointer';
    c.querySelector('.card-b').onclick = () => openPost(p);
    mkChart($('canvas', c), { type: 'bar', data: { labels: incs.map((_, i) => (i + 1) + '日目'), datasets: [{ label: 'その日のリーチ', data: incs, backgroundColor: C1 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false }, ticks: { font: { size: 9 }, maxRotation: 0, autoSkip: true } }, y: { display: false, beginAtZero: true } } } });
  });
}

/* ---- 競合 ---- */
function compRows(D, a, b) {
  const by = Object.fromEntries(D.comp.competitors.map(c => [c.id, c]));
  return D.comp.snapshots.filter(s => s._d >= a && s._d <= b && by[s.competitor_id]).map(s => ({
    _d: s._d, cid: s.competitor_id, name: by[s.competitor_id].name + (by[s.competitor_id].is_self ? '（自分）' : ''), self: by[s.competitor_id].is_self,
    c_followers: s.followers, c_ppw: s.posts_per_week, c_avg_likes: s.avg_likes, c_avg_comments: s.avg_comments, c_er: s.engagement_rate, c_reel: s.reel_share, c_media: s.media_count, _s: s,
  }));
}
const compDims = [
  { key: 'acc', label: 'アカウント', get: r => ({ k: r.cid, l: r.name, o: r.self ? 0 : 1 }) },
  { key: 'date', label: '記録した日', get: (r, c) => ({ k: r._d - c.start, l: ymd(r._d), o: r._d }) },
];
const COMP_METRICS = ['c_followers', 'c_ppw', 'c_avg_likes', 'c_avg_comments', 'c_er', 'c_reel', 'c_media'];
function compChart(parent, rows, title, id) {
  const st = S.ch[id] || (S.ch[id] = { m1: 'c_followers' });
  const c = card(parent, title);
  c.right.innerHTML = `<select aria-label="指標">${metricOptions(COMP_METRICS, st.m1)}</select>`;
  c.body.innerHTML = '<div class="legend"></div><div class="chart-wrap"><canvas></canvas></div>';
  const draw = () => {
    destroyCharts(id);
    const dates = [...new Set(rows.map(r => r._d))].sort((a, b) => a - b);
    const ids = [...new Set(rows.map(r => r.cid))];
    const dsets = ids.map((cid, i) => {
      const rr = rows.filter(r => r.cid === cid); const self = rr[0].self;
      return { label: rr[0].name, data: dates.map(d => { const r = rr.find(x => x._d === d); return r ? r[st.m1] : null; }), borderColor: self ? C1 : SERIES_COLORS[(i % 7) + 1], borderWidth: self ? 3 : 1.5, pointRadius: 2, tension: .15, spanGaps: true, _k: st.m1 };
    });
    $('.legend', c.body).innerHTML = dsets.map(d => `<span><i style="border-color:${d.borderColor}"></i>${esc(d.label)}</span>`).join('');
    mkChart($('canvas', c.body), { type: 'line', data: { labels: dates.map(mds), datasets: dsets }, options: { responsive: true, maintainAspectRatio: false, animation: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${it.dataset.label}: ${fmt(st.m1, it.raw)}` } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: '#eee' }, ticks: { callback: axisFmt(st.m1), maxTicksLimit: 5 } } } } }, id);
  };
  $('select', c.right).onchange = e => { st.m1 = e.target.value; draw(); };
  draw();
}
function noComp(D, body) { body.innerHTML = emptyMsg(D, 'この期間に競合の記録がありません（競合は週1回記録します）。'); }
function renderCompOverview({ D, cur, cmp }, body) {
  const rows = compRows(D, cur[0], cur[1]); if (!rows.length) return noComp(D, body);
  const crows = cmp ? compRows(D, cmp[0], cmp[1]) : null;
  compChart(body, rows, 'フォロワーなどの推移（週1回の記録）', 'comp-ov');
  const t = card(body, null);
  explorer(t.body, { id: 'comp-ov', dims: [compDims[0]], metrics: ['c_followers', 'c_growth', 'c_ppw', 'c_avg_likes', 'c_avg_comments', 'c_er', 'c_reel'], rows, cmpRows: crows && crows.length ? crows : null, sort: 'c_followers' });
}
function renderCompTrend({ D, cur, cmp }, body) {
  const rows = compRows(D, cur[0], cur[1]); if (!rows.length) return noComp(D, body);
  compChart(body, rows, '推移（週1回の記録）', 'comp-tr');
  const t = card(body, null);
  if (!S.tb['comp-tr']) S.tb['comp-tr'] = { dim: 'date', dim2: 'acc', sort: { k: '_dim', d: -1 }, q: '', qmode: 'in', n: 25, page: 0, view: 'table', vm: null };
  explorer(t.body, { id: 'comp-tr', dims: compDims, metrics: COMP_METRICS, rows });
}
function renderCompPosts({ D, cur }, body) {
  const by = Object.fromEntries(D.comp.competitors.map(c => [c.id, c]));
  const seen = new Set(), rows = [];
  D.comp.snapshots.filter(s => s._d >= cur[0] && s._d <= cur[1]).sort((a, b) => b._d - a._d).forEach(s => (s.top_posts || []).forEach(tp => {
    const key = s.competitor_id + '|' + (tp.permalink || tp.date + tp.caption_head); if (seen.has(key) || !by[s.competitor_id]) return; seen.add(key);
    rows.push({ _d: dn(tp.date), cid: s.competitor_id, name: by[s.competitor_id].name + (by[s.competitor_id].is_self ? '（自分）' : ''), tp, posts: 1, top_likes: tp.likes, top_comments: tp.comments });
  }));
  if (!rows.length) return noComp(D, body);
  $('#notice').insertAdjacentHTML('beforeend', '<div class="note info">各アカウントの、記録した日に反応が多かった投稿です（週1回の記録）。いいね・コメントは記録した日の時点の数です。</div>');
  const t = card(body, null);
  explorer(t.body, { id: 'comp-posts', dims: [
    { key: 'post', label: '投稿', get: r => ({ k: r.cid + r.tp.date + r.tp.caption_head, l: `${r.tp.caption_head}（${ymd(r._d)}）` }) },
    { key: 'acc', label: 'アカウント', get: r => ({ k: r.cid, l: r.name }) },
    { key: 'format', label: '形式', get: r => ({ k: r.tp.format, l: r.tp.format || '不明' }) },
    { key: 'wd', label: '投稿した曜日', get: r => ({ k: wdOf(r._d), l: WD[wdOf(r._d)] + '曜日', o: wdOf(r._d) }) }],
    metrics: ['posts', 'top_likes', 'top_comments'], rows, sort: 'top_likes',
    rowClickable: d => d === 'post', onRow: r => { if (r.tp.permalink) window.open(r.tp.permalink, '_blank', 'noopener'); else toast('サンプルのため Instagram へのリンクはありません'); } });
}

/* ---- 確認待ち ---- */
function renderReview(D, body) {
  const n = D.review.filter(x => x.status === 'pending').length;
  body.innerHTML = `<div class="empty"><strong>準備中です</strong>投稿する前の内容を、ここで確認・承認できるようにする予定です。<br>いま確認待ちの投稿: ${n}件${D.acc.sample ? '（サンプル）' : ''}</div>`;
}

/* ================= 説明の吹き出し ================= */
function setupTips() {
  const tip = $('#tip'); let cur = null;
  const show = el => {
    cur = el; tip.innerHTML = (el.dataset.tipTitle ? `<b>${esc(el.dataset.tipTitle)}</b>` : '') + esc(el.dataset.tip); tip.hidden = false;
    const r = el.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = Math.min(Math.max(8, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 8), y = r.bottom + 6;
    if (y + th > window.innerHeight - 8) y = r.top - th - 6;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  };
  const hide = () => { cur = null; tip.hidden = true; };
  document.addEventListener('mouseover', e => { const el = e.target.closest('[data-tip]'); if (el && el !== cur) show(el); else if (!el && cur) hide(); });
  document.addEventListener('focusin', e => { const el = e.target.closest('[data-tip]'); if (el) show(el); });
  document.addEventListener('touchstart', e => { const el = e.target.closest('[data-tip]'); if (el) show(el); else hide(); }, { passive: true });
  window.addEventListener('scroll', hide, true);
}

/* ================= 起動 ================= */
async function switchAccount(id) {
  S.acc = id; store.set('acc', id);
  const acc = S.accounts.find(a => a.id === id);
  $('#sampleBadge').hidden = !acc.sample;
  $('#body').innerHTML = '<div class="empty">読み込み中…</div>';
  try { await loadAccount(acc); } catch (e) { $('#body').innerHTML = `<div class="empty"><strong>データを読み込めませんでした</strong>${esc(e.message)}</div>`; return; }
  render();
}
async function main() {
  renderNav(); setupTips();
  $('#menuBtn').onclick = () => { const o = document.body.classList.toggle('nav-open'); $('#menuBtn').setAttribute('aria-expanded', o); };
  $('#scrim').onclick = () => document.body.classList.remove('nav-open');
  $('#drBtn').onclick = e => { e.stopPropagation(); $('#drPanel').hidden ? openDr() : closeDr(); };
  document.addEventListener('click', e => { if (!$('#drPanel').hidden && !e.target.closest('#dr')) closeDr(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeDr(); closeModal(); document.body.classList.remove('nav-open'); } });
  window.addEventListener('hashchange', () => { S.report = (location.hash || '#home').slice(1); if (!navInfo(S.report)) S.report = 'home'; render(); });
  let idx;
  try { idx = await getJSON('data/accounts.json'); } catch (e) { $('#title').textContent = 'エラー'; $('#body').innerHTML = `<div class="empty"><strong>データを読み込めませんでした</strong>${esc(e.message)}</div>`; return; }
  S.accounts = idx.accounts || [];
  if (!S.accounts.length) { $('#body').innerHTML = '<div class="empty"><strong>アカウントがまだありません</strong></div>'; return; }
  const sel = $('#accSel');
  sel.innerHTML = S.accounts.map(a => `<option value="${esc(a.id)}">${esc(a.name)}（${esc(a.kind)}）@${esc(a.username)}</option>`).join('');
  const saved = store.get('acc'); const first = S.accounts.find(a => a.id === saved) ? saved : S.accounts[0].id;
  sel.value = first; sel.onchange = () => switchAccount(sel.value);
  S.range = presetRange(S.preset); applyCmp(); drLabel();
  S.report = (location.hash || '#home').slice(1); if (!navInfo(S.report)) S.report = 'home';
  switchAccount(first);
}
main();
