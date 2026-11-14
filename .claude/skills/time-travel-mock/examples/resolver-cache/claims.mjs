// Domain claims for the resolver-cache example: the headline conclusions, checked over every legal schedule of the model.
// Used as:  node scripts/check_contract.mjs PAGE.html --claims examples/resolver-cache/claims.mjs
export default (E, {ok, eq, run, agg}) => {
  const a1 = agg('perop', 'same');
  ok(a1.dupPaths > 0 && a1.dupPaths < a1.paths, 'variant 1, same key: some but not all schedules duplicate the lookup');
  eq([agg('coarse', 'same').dupPaths, agg('coalesce', 'same').dupPaths], [0, 0], 'variants 2 and 3, same key: no schedule duplicates');
  eq([agg('coarse', 'same').lkMin, agg('coarse', 'same').lkMax], [1, 1], 'variant 2, same key: always exactly 1 lookup');
  eq([agg('coalesce', 'same').lkMin, agg('coalesce', 'same').lkMax], [1, 1], 'variant 3, same key: always exactly 1 lookup');
  ok(agg('coarse', 'diff').waitBMax >= 100, 'variant 2: an unrelated key can wait behind the slow lookup');
  ok(agg('coalesce', 'diff').waitBMax < 5 && agg('perop', 'diff').waitBMax < 5, 'variants 1 and 3: an unrelated key never waits more than the brief mutex hold');
  let r = run('perop', 'same', 'dup');
  eq([r.m.lookups, r.m.dups, r.ev[5].dup], [2, 1, 'concurrent'], 'variant 1, "both miss" schedule: two lookups, flagged concurrent duplicate');
  eq(run('perop', 'same', 'stale').ev.find(e => e.dup).dup, 'stale', 'variant 1, "paused after miss" schedule: flagged stale');
  eq(run('perop', 'same', 'serial').m.lookups, 1, 'variant 1, serial schedule: 1 lookup (the schedule single-threaded tests see)');
  r = run('coalesce', 'same', 'dup'); ok(r.ev.some(e => e.flags.includes('join')) && r.m.lookups === 1, 'variant 3: the second caller joins the in-flight lookup');
};
