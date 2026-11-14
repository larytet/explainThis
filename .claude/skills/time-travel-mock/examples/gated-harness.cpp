// Cross-check for the Time-Travel mock (NOT part of the page, NOT evidence shown in it).
// Compiles the exact C++ text displayed on the page (variantN.inc, written by `node check.mjs <dir>`) and forces the
// key schedules with a gate on slow_lookup, using real threads. Build: see README.md in this directory's parent.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <functional>
#include <future>
#include <mutex>
#include <string>
#include <thread>

using namespace std::chrono_literals;

// ---- test seam: slow_lookup is declared by the variant text and defined here ----
static std::atomic<int> g_calls{0};
static std::mutex g_gm; static std::condition_variable g_gcv;
static std::string g_hold_key;            // lookups of this key block until released
static bool g_open = true;
static std::string g_throw_key;           // lookups of this key throw once
static std::atomic<bool> g_thrown{false};
std::string slow_lookup(const std::string& host) {
    ++g_calls;
    if (host == g_throw_key && !g_thrown.exchange(true)) throw std::runtime_error("lookup failed");
    std::unique_lock<std::mutex> l(g_gm);
    g_gcv.wait(l, [&] { return g_open || host != g_hold_key; });
    return "ip(" + host + ")";
}
static void hold(const std::string& k) { std::lock_guard<std::mutex> l(g_gm); g_hold_key = k; g_open = false; }
static void release() { { std::lock_guard<std::mutex> l(g_gm); g_open = true; } g_gcv.notify_all(); }
static void reset() { g_calls = 0; g_hold_key.clear(); g_open = true; g_throw_key.clear(); g_thrown = false; }
static bool wait_until(std::function<bool()> p, std::chrono::milliseconds d) {
    auto end = std::chrono::steady_clock::now() + d;
    while (std::chrono::steady_clock::now() < end) { if (p()) return true; std::this_thread::sleep_for(2ms); }
    return p();
}

#include VARIANT_FILE

int main() {
    // Case 1: same key, first lookup held open, second caller arrives
    { reset(); Resolver r; hold("db");
      std::string ra, rb; std::atomic<bool> bdone{false};
      std::thread a([&] { ra = r.resolve("db"); });
      wait_until([] { return g_calls.load() >= 1; }, 2000ms);
      std::thread b([&] { rb = r.resolve("db"); bdone = true; });
      wait_until([] { return g_calls.load() >= 2; }, 300ms);   // does B start its own lookup?
      int calls_while_held = g_calls.load(); bool b_done_while_held = bdone.load();
      release(); a.join(); b.join();
      std::printf("case1 same-key   lookups_while_A_held=%d total=%d B_returned_while_A_held=%d results_equal=%d\n", calls_while_held, g_calls.load(), (int)b_done_while_held, (int)(ra == rb)); }
    // Case 2: unrelated key while a slow lookup is open
    { reset(); Resolver r; hold("db"); std::atomic<bool> bdone{false};
      std::thread a([&] { r.resolve("db"); });
      wait_until([] { return g_calls.load() >= 1; }, 2000ms);
      std::thread b([&] { r.resolve("cdn"); bdone = true; });
      bool done = wait_until([&] { return bdone.load(); }, 300ms);
      release(); a.join(); b.join();
      std::printf("case2 other-key  B_returned_within_300ms_while_A_held=%d\n", (int)done); }
    // (The page's "stale miss" schedule needs a pause between get() and put() inside the cache; there is no seam for that here.)
    // Case 4: exception from the lookup, then retry
    { reset(); Resolver r; g_throw_key = "bad";
      std::string first = "ok", second = "ok";
      try { r.resolve("bad"); } catch (const std::exception& e) { first = e.what(); }
      try { r.resolve("bad"); } catch (const std::exception& e) { second = e.what(); }
      std::printf("case4 exception  first=[%s] second=[%s] lookups=%d\n", first.c_str(), second.c_str(), g_calls.load()); }
    // Case 5: follower blocked while leader's lookup throws (variant 3 only is interesting)
    { reset(); Resolver r; hold("bad2"); g_throw_key = "bad2"; std::string fol = "ok";
      std::thread a([&] { try { r.resolve("bad2"); } catch (...) {} });
      wait_until([] { return g_calls.load() >= 1; }, 2000ms);
      std::thread b([&] { try { r.resolve("bad2"); } catch (const std::exception& e) { fol = e.what(); } });
      std::this_thread::sleep_for(100ms); release(); a.join(); b.join();
      std::printf("case5 follower   B_outcome=[%s] lookups=%d\n", fol.c_str(), g_calls.load()); }
    return 0;
}
