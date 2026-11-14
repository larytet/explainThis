// Engine checks for the Time-Travel mock. No dependencies: node check.mjs
// Extracts <script id="engine"> from index.html and tests the state machine on its own (no DOM).
// Also writes the three supplied C++ variants to a directory (argv[2]) so the g++ harness can compile exactly the text shown on the page.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(dir, 'index.html'), 'utf8');
const m = html.match(/<script id="engine">([\s\S]*?)<\/script>/);
const E = new Function('module', m[1] + '\nreturn module.exports;')({exports: {}});

let fails = 0, passes = 0;
const ok = (c, msg) => { if (c) passes++; else { fails++; console.log('FAIL ' + msg); } };
const eq = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b), msg + ' (got ' + JSON.stringify(a) + ', want ' + JSON.stringify(b) + ')');

if (process.argv[2]) {
  fs.mkdirSync(process.argv[2], {recursive: true});
  for (const v of Object.values(E.VARIANTS)) fs.writeFileSync(path.join(process.argv[2], 'variant' + v.n + '.inc'), v.src.map(l => l.t).join('\n') + '\n');
}

const run = (v, w, s) => { const ch = E.autoRun(v, w, s, []); const rp = E.replay(v, w, ch); return {ch, rp, m: E.metrics(rp.states.at(-1)), s: rp.states.at(-1), ev: rp.events}; };

// 1. every variant x workload x schedule terminates with both threads done, correct values, nothing left in flight
for (const v of Object.keys(E.VARIANTS)) for (const w of Object.keys(E.WORKLOADS)) for (const s of Object.keys(E.SCHEDULES)) {
  const r = run(v, w, s), W = E.WORKLOADS[w], tag = `${v}/${w}/${s}`;
  ok(E.allDone(r.s), tag + ' terminates');
  for (const t of E.THREADS) eq(r.s.th[t].result, W.val[W.keys[t]], tag + ' result of ' + t);
  eq(Object.keys(r.s.inflight), [], tag + ' no in-flight entry left');
  ok(r.s.mu.owner === null, tag + ' mutex released');
  for (const t of E.THREADS) ok(Object.keys(r.s.cache).includes(W.keys[t]), tag + ' cache holds ' + W.keys[t]);
  ok(r.s.lookups.every(l => l.consumed), tag + ' every lookup consumed');
}

// 2. exhaustive exploration: no deadlock anywhere; key claims hold over ALL schedules
const agg = (v, w) => E.aggregate(E.init(v, w));
for (const v of Object.keys(E.VARIANTS)) for (const w of Object.keys(E.WORKLOADS)) {
  const a = agg(v, w); ok(a.dead === 0, `${v}/${w}: no reachable deadlock (paths ${a.paths})`);
}
ok(agg('perop', 'same').dupPaths > 0 && agg('perop', 'same').dupPaths < agg('perop', 'same').paths, 'variant 1 same key: some, not all, schedules duplicate');
eq(agg('coarse', 'same').dupPaths, 0, 'variant 2 same key: no schedule duplicates');
eq(agg('coalesce', 'same').dupPaths, 0, 'variant 3 same key: no schedule duplicates');
eq([agg('coarse', 'same').lkMin, agg('coarse', 'same').lkMax], [1, 1], 'variant 2 same key: always exactly 1 lookup');
eq([agg('coalesce', 'same').lkMin, agg('coalesce', 'same').lkMax], [1, 1], 'variant 3 same key: always exactly 1 lookup');
eq([agg('perop', 'same').lkMin, agg('perop', 'same').lkMax], [1, 2], 'variant 1 same key: 1 or 2 lookups');
for (const v of Object.keys(E.VARIANTS)) eq(agg(v, 'diff').dupPaths, 0, v + ' different keys: never a duplicate');
ok(agg('coarse', 'diff').waitBMax >= 100, 'variant 2 different keys: B can wait >= 100');
ok(agg('coalesce', 'diff').waitBMax < 5, 'variant 3 different keys: B never waits more than 4 (brief mutex only), max=' + agg('coalesce', 'diff').waitBMax);
ok(agg('perop', 'diff').waitBMax < 5, 'variant 1 different keys: B never waits more than 4, max=' + agg('perop', 'diff').waitBMax);
ok(agg('coarse', 'hit').waitBMax >= 100, 'variant 2: an unrelated CACHE HIT can wait >= 100');
ok(agg('coalesce', 'hit').waitBMax < 5 && agg('perop', 'hit').waitBMax < 5, 'variants 1 and 3: unrelated hit waits < 5');
console.log('paths: ' + Object.keys(E.VARIANTS).map(v => v + '=' + ['same', 'diff', 'hit'].map(w => agg(v, w).paths + '(' + agg(v, w).dupPaths + ' dup)').join('/')).join('  '));

// 3. named scenarios from the narrative
let r = run('perop', 'same', 'dup');
eq(r.m.lookups, 2, 'v1 dup schedule: 2 lookups'); eq(r.m.dups, 1, 'v1 dup schedule: 1 duplicate');
eq(r.ev.slice(0, 4).map(e => e.actor + ':' + e.op + ':' + e.flags.join()), ['A:lock:', 'A:get:miss', 'B:lock:', 'B:get:miss'], 'v1 dup: A locks, A misses, B locks, B misses');
eq(r.ev[4].op + r.ev[5].op, 'lstartlstart', 'v1 dup: A starts lookup then B starts duplicate lookup');
eq(r.ev[5].dup, 'concurrent', 'v1 dup: second lookup flagged concurrent duplicate');
r = run('perop', 'same', 'stale'); eq(r.m.lookups, 2, 'v1 stale schedule: 2 lookups'); eq(r.ev.find(e => e.dup).dup, 'stale', 'v1 stale: flagged stale');
r = run('perop', 'same', 'serial'); eq(r.m.lookups, 1, 'v1 serial: 1 lookup');
r = run('coarse', 'same', 'dup'); eq(r.m.lookups, 1, 'v2 dup: 1 lookup'); ok(r.m.waitB >= 100, 'v2 dup: B waited >= 100 on mu_ (' + r.m.waitB + ')'); eq(r.m.waitFuture.B, 0, 'v2: no future wait');
r = run('coarse', 'diff', 'dup'); ok(r.m.waitMutex.B >= 100, 'v2 diff: unrelated key B waits ' + r.m.waitMutex.B + ' on mu_'); ok(r.m.finish.B > 120, 'v2 diff: B ends after 120, was ' + r.m.finish.B);
r = run('coalesce', 'same', 'dup'); eq(r.m.lookups, 1, 'v3 dup: 1 lookup'); ok(r.m.waitFuture.B >= 100, 'v3 same: B waits on the shared future'); ok(r.ev.some(e => e.flags.includes('join')), 'v3: B joined');
eq(r.m.waitMutex.A, 0, 'v3 same: leader never waits on mu_');
r = run('coalesce', 'diff', 'dup'); ok(r.m.finish.B < 30, 'v3 diff: B finishes at ' + r.m.finish.B); ok(r.m.finish.A >= 100, 'v3 diff: A finishes at ' + r.m.finish.A);
r = run('perop', 'diff', 'dup'); ok(r.m.finish.B < 30, 'v1 diff: B finishes at ' + r.m.finish.B);
// work and time accounting
r = run('perop', 'same', 'dup'); eq(r.m.work, 200, 'v1 dup: lookup work 200'); r = run('coalesce', 'same', 'dup'); eq(r.m.work, 100, 'v3 dup: lookup work 100');

// 4. impossible transitions are rejected with an explanation, and are not recorded
{
  let s = E.step(E.init('coarse', 'same'), 'A').state;
  let err; try { E.step(s, 'B'); } catch (e) { err = e; }
  ok(err && /mu_ is held by A/.test(err.message) && err.info.kind === 'mutex', 'v2: B rejected with explanation');
  try { E.step(s, 'T'); err = null; } catch (e) { err = e; } ok(err && /nothing to wait for/.test(err.message), 'clock rejected when no lookup in flight');
  s = E.init('coalesce', 'same'); for (const a of ['A', 'A', 'B', 'B']) s = E.step(s, a).state;
  try { E.step(s, 'B'); err = null; } catch (e) { err = e; } ok(err && err.info.kind === 'future' && /set_value/.test(err.message), 'v3: follower rejected while leader has not set_value');
  s = E.init('perop', 'same'); for (const a of ['A', 'A', 'A']) s = E.step(s, a).state;
  try { E.step(s, 'A'); err = null; } catch (e) { err = e; } ok(err && err.info.kind === 'timer', 'A cannot finish lookup before it is due');
  const f = run('perop', 'same', 'serial').s;
  try { E.step(f, 'A'); err = null; } catch (e) { err = e; } ok(err && err.info.kind === 'done', 'finished thread rejected');
}

// 5. replay (rewind) reconstructs state from events: every prefix equals an independent fold, and the state is a pure function of the choices
for (const v of Object.keys(E.VARIANTS)) for (const s of Object.keys(E.SCHEDULES)) {
  const w = 'same', ch = E.autoRun(v, w, s, []), rp = E.replay(v, w, ch);
  let st = E.init(v, w), good = true;
  ch.forEach((c, i) => { st = E.step(st, c).state; if (JSON.stringify(st) !== JSON.stringify(rp.states[i + 1])) good = false; if (JSON.stringify(E.replay(v, w, ch.slice(0, i + 1)).states.at(-1)) !== JSON.stringify(st)) good = false; });
  ok(good, `${v}/${s}: every prefix replay equals the incremental fold`);
  // time never goes backwards, counters never decrease
  let mono = true, prev = rp.states[0]; for (const x of rp.states.slice(1)) { if (x.now < prev.now || x.lookups.length < prev.lookups.length || x.dups < prev.dups) mono = false; prev = x; }
  ok(mono, `${v}/${s}: time, lookups, duplicates are monotone`);
}
// replay through the whole exhaustive tree would be redundant; instead sample 200 random schedules and check invariants
let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
for (const v of Object.keys(E.VARIANTS)) for (const w of Object.keys(E.WORKLOADS)) for (let n = 0; n < 60; n++) {
  let s = E.init(v, w); let good = true; const ch = [];
  while (!E.allDone(s)) {
    const ks = E.ACTORS.filter(a => E.runnable(s, a).ok); if (!ks.length) { good = false; break; }
    const a = ks[Math.floor(rnd() * ks.length)]; ch.push(a); s = E.step(s, a).state; // step() throws if an op ran without holding mu_
    const holders = E.THREADS.filter(t => { const th = s.th[t]; return !th.done && s.mu.owner === t; });
    if (holders.length > 1) good = false;
    for (const l of s.lookups) if (l.due < l.start) good = false;
  }
  ok(good && E.allDone(s), `${v}/${w}: random schedule ${n} completes without invariant violation`);
  if (n < 5) { const fresh = E.replay(v, w, ch).states.at(-1); ok(JSON.stringify(fresh) === JSON.stringify(s), `${v}/${w}: random schedule replays identically`); }
}

// 6. guided chapters: cursors are in range and the claims the text relies on hold
E.CHAPTERS.forEach((c, i) => {
  const ch = E.autoRun(c.variant, c.workload, c.sched, []), n = ch.length;
  const to = c.to === 'end' ? n : c.to;
  ok(c.from <= to && to <= n, `chapter ${i + 1} (${c.id}) cursor range ${c.from}..${to} within 0..${n}`);
  ok(typeof c.a({m: run(c.variant, c.workload, c.sched).m, agg: agg(c.variant, c.workload)}) === 'string', `chapter ${i + 1} answer renders`);
});
{ // chapter-specific facts
  const st = (c, k) => E.replay(c.variant, c.workload, E.autoRun(c.variant, c.workload, c.sched, []).slice(0, k)).states.at(-1);
  const C = Object.fromEntries(E.CHAPTERS.map(c => [c.id, c]));
  let s = st(C.bothmiss, C.bothmiss.from); ok(s.th.A.local.miss && !s.th.B.local.miss && s.mu.owner === null && !Object.keys(s.cache).length, 'ch bothmiss start: A missed, lock free, cache empty');
  s = st(C.bothmiss, C.bothmiss.to); ok(s.th.A.local.miss && s.th.B.local.miss && s.lookups.length === 0, 'ch bothmiss end: both missed, no lookup yet');
  s = st(C.dup, C.dup.to); eq([s.lookups.length, s.dups], [2, 1], 'ch dup end: two lookups in flight, 1 duplicate');
  s = st(C.coarse, C.coarse.from); ok(s.mu.owner === 'A' && s.th.B.blocked && s.th.B.blocked.on === 'mutex' && s.lookups.length === 1, 'ch coarse start: A holds mu_ inside the lookup, B blocked');
  s = st(C.coarsediff, C.coarsediff.from); ok(s.th.B.key === 'cdn.internal' && s.th.B.blocked, 'ch coarsediff start: unrelated key B blocked');
  s = st(C.coalesce, C.coalesce.from); ok(s.inflight['db.internal'] && s.mu.owner === null, 'ch coalesce start: A registered in-flight and released the lock');
  s = st(C.coalesce, 4); ok(s.th.B.local.role === 'follower', 'ch coalesce: B follower after its decide');
}

// 7. every line id used by an op exists in the listing, scopes resolve, line numbers unique
for (const v of Object.values(E.VARIANTS)) {
  const ids = v.src.map(l => l.id).filter(Boolean); eq(new Set(ids).size, ids.length, v.id + ' line ids unique');
  for (const o of v.prog) for (const l of o.lines) ok(v.lineNo[l], `${v.id}/${o.id}: line id ${l} exists`);
  for (const [a, b] of v.scopes) ok(v.lineNo[a] && v.lineNo[b] && v.lineNo[a] < v.lineNo[b], v.id + ' scope ' + a + '..' + b);
  ok(!v.src.some(l => l.t.includes('//@')), v.id + ' markers stripped from display text');
}
// dynamic line lists used by events also exist
for (const v of Object.keys(E.VARIANTS)) for (const w of Object.keys(E.WORKLOADS)) for (const s of Object.keys(E.SCHEDULES)) for (const e of run(v, w, s).ev) for (const l of e.lines) ok(E.VARIANTS[v].lineNo[l], `${v}: event line id ${l} exists`);

console.log(`${passes} passed, ${fails} failed`);
process.exit(fails ? 1 : 0);
