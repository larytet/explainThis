// Contract and soundness checks for the engine inside a time-travel page. No dependencies.
// usage: node check_contract.mjs PAGE.html [--claims claims.mjs] [--emit DIR]
// Domain-specific claims go in claims.mjs: `export default (E, h) => { h.ok(cond, msg); h.eq(a, b, msg); h.run(variant, workload, sched) }`.
// --emit DIR writes the supplied listings (variantN.inc: the exact text shown on the page) for compiling or for a gated harness.
import fs from 'node:fs'; import path from 'node:path';
const args = process.argv.slice(2); const page = args[0];
if (!page) { console.log('usage: node check_contract.mjs PAGE.html [--claims claims.mjs] [--emit DIR]'); process.exit(2); }
const opt = n => args.includes(n) ? args[args.indexOf(n) + 1] : null;
const html = fs.readFileSync(page, 'utf8');
const m = html.match(/<script id="engine">([\s\S]*?)<\/script>/);
if (!m) { console.log('FAIL no <script id="engine"> block'); process.exit(1); }
const E = new Function('module', m[1] + '\nreturn module.exports;')({exports: {}});
let fails = 0, passes = 0;
const ok = (c, msg) => { if (c) passes++; else { fails++; console.log('FAIL ' + msg); } };
const eq = (a, b, msg) => ok(JSON.stringify(a) === JSON.stringify(b), msg + ' (got ' + JSON.stringify(a) + ', want ' + JSON.stringify(b) + ')');
const J = JSON.stringify;

// 0. the UI contract: names and shapes the page script depends on (see references/model-contract.md)
for (const k of ['ACTORS', 'VARIANTS', 'WORKLOADS', 'SCHEDULES', 'CHAPTERS', 'init', 'runnable', 'status', 'step', 'replay', 'pick', 'autoRun', 'metrics', 'aggregate', 'allDone', 'describeNext', 'pending'])
  ok(E[k] !== undefined, 'engine exports ' + k);
if (fails) { console.log(`${passes} passed, ${fails} failed`); process.exit(1); }
const V = E.VARIANTS, W = E.WORKLOADS, S = E.SCHEDULES;
const run = (v, w, s) => { const ch = E.autoRun(v, w, s, []); const rp = E.replay(v, w, ch); return {ch, rp, s: rp.states.at(-1), ev: rp.events, m: E.metrics(rp.states.at(-1))}; };

// 1. listings: ids unique, markers stripped, every op/event line id exists, scopes resolve
for (const v of Object.values(V)) {
  ok(Array.isArray(v.src) && v.src.length && v.src.every(l => typeof l.t === 'string'), v.id + ': src is [{t,id}]');
  const ids = v.src.map(l => l.id).filter(Boolean); eq(new Set(ids).size, ids.length, v.id + ' line ids unique');
  ok(!v.src.some(l => l.t.includes('//@')), v.id + ' //@ markers stripped from displayed text');
  for (const o of v.prog) for (const l of o.lines) ok(v.lineNo[l], `${v.id}/${o.id}: line id ${l} exists`);
  for (const [a, b] of v.scopes || []) ok(v.lineNo[a] && v.lineNo[b] && v.lineNo[a] < v.lineNo[b], `${v.id} scope ${a}..${b}`);
  if (opt('--emit')) { fs.mkdirSync(opt('--emit'), {recursive: true}); fs.writeFileSync(path.join(opt('--emit'), 'variant' + v.n + '.inc'), v.src.map(l => l.t).join('\n') + '\n'); }
}

// 2. every variant x workload x named schedule terminates correctly; replay is a pure function of the choices
for (const v of Object.keys(V)) for (const w of Object.keys(W)) for (const s of Object.keys(S)) {
  const tag = `${v}/${w}/${s}`, r = run(v, w, s);
  ok(E.allDone(r.s), tag + ' terminates with every thread done');
  let st = E.init(v, w), good = true, mono = true, prev = r.rp.states[0];
  r.ch.forEach((c, i) => { st = E.step(st, c).state; if (J(st) !== J(r.rp.states[i + 1])) good = false; if (J(E.replay(v, w, r.ch.slice(0, i + 1)).states.at(-1)) !== J(st)) good = false; });
  ok(good, tag + ': every prefix replay equals the incremental fold');
  for (const x of r.rp.states.slice(1)) { if (x.now < prev.now) mono = false; prev = x; }
  ok(mono, tag + ': time never goes backwards');
  for (const e of r.ev) for (const l of e.lines || []) ok(V[v].lineNo[l], `${tag}: event line id ${l} exists`);
}

// 3. exhaustive exploration of every legal schedule: no deadlock (a model that can wedge is a bug in the model)
for (const v of Object.keys(V)) for (const w of Object.keys(W)) { const a = E.aggregate(E.init(v, w)); ok(a.dead === 0, `${v}/${w}: no reachable deadlock over ${a.paths} orderings`); }

// 4. random schedules complete (cheap second opinion on the exhaustive pass)
let seed = 12345; const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
for (const v of Object.keys(V)) for (const w of Object.keys(W)) for (let n = 0; n < 40; n++) {
  let s = E.init(v, w), good = true;
  while (!E.allDone(s)) { const ks = E.ACTORS.filter(a => E.runnable(s, a).ok); if (!ks.length) { good = false; break; } s = E.step(s, ks[Math.floor(rnd() * ks.length)]).state; }
  ok(good, `${v}/${w}: random schedule ${n} completes`);
}

// 5. rejection: every non-runnable actor must explain itself, and stepping it must throw without side effects
for (const v of Object.keys(V)) for (const w of Object.keys(W)) {
  let s = E.init(v, w); const ch = E.autoRun(v, w, Object.keys(S)[0], []);
  for (const c of ch) { for (const a of E.ACTORS) { const r = E.runnable(s, a); if (!r.ok) { ok(typeof r.reason === 'string' && r.reason.length > 20, `${v}/${w}: ${a} blocked with a reason`); let t = false; try { E.step(s, a); } catch (e) { t = true; } ok(t, `${v}/${w}: stepping blocked ${a} throws`); } } s = E.step(s, c).state; }
}

// 6. guided chapters
E.CHAPTERS.forEach((c, i) => {
  const n = E.autoRun(c.variant, c.workload, c.sched, []).length, to = c.to === 'end' ? n : c.to;
  ok(V[c.variant] && W[c.workload] && S[c.sched], `chapter ${i + 1} (${c.id}) names a real variant, workload, schedule`);
  ok(c.from <= to && to <= n, `chapter ${i + 1} cursor range ${c.from}..${to} within 0..${n}`);
  const r = run(c.variant, c.workload, c.sched);
  ok(typeof c.a({m: r.m, agg: E.aggregate(E.init(c.variant, c.workload))}) === 'string', `chapter ${i + 1} answer renders`);
});

// 7. domain claims
if (opt('--claims')) { const mod = await import(path.resolve(opt('--claims'))); mod.default(E, {ok, eq, run, agg: (v, w) => E.aggregate(E.init(v, w))}); }
console.log(`${passes} passed, ${fails} failed`); process.exit(fails ? 1 : 0);
