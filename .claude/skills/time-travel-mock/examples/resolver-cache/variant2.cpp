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
        std::lock_guard<std::mutex> lock(mu_);   // held until return
        auto it = map_.find(host);
        if (it != map_.end()) return it->second;  // hit
        std::string ip = slow_lookup(host);      // mu_ STILL HELD
        map_[host] = ip;
        return ip;                               // releases mu_
    }
private:
    std::mutex mu_;
    std::unordered_map<std::string, std::string> map_;
};
