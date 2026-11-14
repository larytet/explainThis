#include <future>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>

std::string slow_lookup(const std::string& host);  // ~100 ms (DNS, say); defined elsewhere

class Resolver {
public:
    std::string resolve(const std::string& host) {
        std::promise<std::string> promise;
        std::shared_future<std::string> future;
        bool leader = false;
        {
            std::lock_guard<std::mutex> lock(mu_);   // short critical section
            if (auto it = map_.find(host); it != map_.end())
                return it->second;                   // hit
            if (auto it = inflight_.find(host); it != inflight_.end()) {
                future = it->second;                 // join the lookup already running
            } else {
                future = promise.get_future().share();
                inflight_.emplace(host, future);     // we are the leader for this key
                leader = true;
            }
        }                                            // releases mu_
        if (!leader) return future.get();            // wait OUTSIDE the lock
        std::string ip = slow_lookup(host);          // no lock held
        {
            std::lock_guard<std::mutex> lock(mu_);   // takes mu_ again
            map_[host] = ip;
            inflight_.erase(host);
        }                                            // releases mu_
        promise.set_value(ip);                       // wakes the followers
        return ip;
    }
    // NOT HANDLED (see "Model and limits"): slow_lookup() throwing, timeouts,
    // cancellation, eviction, and cleanup of inflight_ entries on failure.
private:
    std::mutex mu_;
    std::unordered_map<std::string, std::string> map_;
    std::unordered_map<std::string, std::shared_future<std::string>> inflight_;
};
