#include <future>
#include <mutex>
#include <optional>
#include <string>
#include <unordered_map>
#include <utility>

std::string slow_lookup(const std::string& host);  // ~100 ms (DNS, say); defined elsewhere

class Cache {
public:
    std::optional<std::string> get(const std::string& key) {
        std::lock_guard<std::mutex> lock(mu_);   // takes mu_
        auto it = map_.find(key);
        if (it == map_.end()) return std::nullopt;  // miss
        return it->second;                       // hit
    }                                            // releases mu_
    void put(const std::string& key, std::string value) {
        std::lock_guard<std::mutex> lock(mu_);   // takes mu_
        map_[key] = std::move(value);
    }                                            // releases mu_
private:
    std::mutex mu_;
    std::unordered_map<std::string, std::string> map_;
};

class Resolver {
public:
    std::string resolve(const std::string& host) {
        if (auto hit = cache_.get(host)) return *hit;
        std::string ip = slow_lookup(host);      // no lock held
        cache_.put(host, ip);
        return ip;
    }
private:
    Cache cache_;
};
