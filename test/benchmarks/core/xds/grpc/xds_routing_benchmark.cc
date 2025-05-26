#include "benchmark/benchmark.h"

#include "src/core/xds/grpc/xds_routing.h"
#include "src/core/xds/grpc/xds_route_config.h"

// TODO(asheshvidyut): Find and include the actual headers for these
// For now, let's define them here for the benchmark to compile.
enum MatchType {
  EXACT_MATCH,
  SUFFIX_MATCH,
  PREFIX_MATCH,
  UNIVERSAL_MATCH,
  INVALID_MATCH
};

MatchType DomainPatternMatchType(const std::string& /*domain_pattern*/) {
  // Simple mock implementation
  return EXACT_MATCH;
}

bool DomainMatch(MatchType /*match_type*/, const std::string& /*domain_pattern*/, absl::string_view /*domain*/) {
  // Simple mock implementation
  return true;
}


namespace grpc_core {
namespace {

class MockVirtualHostListIterator : public XdsRouting::VirtualHostListIterator {
 public:
  size_t Size() const override { return virtual_hosts_.size(); }

  const std::vector<std::string>& GetDomainsForVirtualHost(
      size_t index) const override {
    return virtual_hosts_[index].domains;
  }

  void AddVirtualHost(XdsRouteConfigResource::VirtualHost vhost) {
    virtual_hosts_.push_back(std::move(vhost));
  }

 private:
  std::vector<XdsRouteConfigResource::VirtualHost> virtual_hosts_;
};

static void BM_FindVirtualHostForDomain(benchmark::State& state) {
  MockVirtualHostListIterator vhost_iterator;

  // Populate vhost_iterator with 1000 diverse virtual hosts
  for (int i = 0; i < 1000; ++i) {
    XdsRouteConfigResource::VirtualHost vhost;
    std::string domain_base = "vhost" + std::to_string(i) + ".example.com";
    // Add a mix of exact, prefix, and suffix matches
    if (i % 3 == 0) {
      vhost.domains = {domain_base}; // Exact match
    } else if (i % 3 == 1) {
      vhost.domains = {"*" + domain_base}; // Suffix match
    } else {
      vhost.domains = {domain_base + "*"}; // Prefix match
    }
    // Occasionally add a second domain pattern to a virtual host
    if (i % 10 == 0) {
        vhost.domains.push_back("another.pattern" + std::to_string(i) + ".com");
    }
    vhost_iterator.AddVirtualHost(std::move(vhost));
  }

  // Keep a few specific virtual hosts for targeted testing if needed
  XdsRouteConfigResource::VirtualHost vhost_exact;
  vhost_exact.domains = {"exact.special.com"};
  vhost_iterator.AddVirtualHost(vhost_exact);

  XdsRouteConfigResource::VirtualHost vhost_suffix;
  vhost_suffix.domains = {"*.suffix.special.com"};
  vhost_iterator.AddVirtualHost(vhost_suffix);

  XdsRouteConfigResource::VirtualHost vhost_prefix;
  vhost_prefix.domains = {"prefix.special.com*"};
  vhost_iterator.AddVirtualHost(vhost_prefix);

  XdsRouteConfigResource::VirtualHost vhost_universal;
  vhost_universal.domains = {"*"}; // Universal match
  vhost_iterator.AddVirtualHost(vhost_universal);


  std::vector<std::string> domains_to_match = {
      "vhost0.example.com", // Matches first generated host
      "test.vhost1.example.com", // Matches second generated host (suffix)
      "vhost2.example.com.test", // Matches third generated host (prefix)
      "exact.special.com",
      "test.suffix.special.com",
      "prefix.special.com.test",
      "unknown.domain.com", // Should match universal or nothing if no universal
      "another.pattern0.com"
  };
  // Add some domains that would match within the 1000 generated hosts
  for (int i = 0; i < 50; ++i) {
    domains_to_match.push_back("vhost" + std::to_string(i * 20) + ".example.com");
     domains_to_match.push_back("sub.vhost" + std::to_string(i * 20 + 1) + ".example.com");
     domains_to_match.push_back("vhost" + std::to_string(i * 20 + 2) + ".example.com.extra");
  }


  for (auto _ : state) {
    for (const auto& domain : domains_to_match) {
      benchmark::DoNotOptimize(
          XdsRouting::FindVirtualHostForDomain(vhost_iterator, domain));
    }
  }
}
BENCHMARK(BM_FindVirtualHostForDomain);

}  // namespace
}  // namespace grpc_core

// TODO(asheshvidyut): Uncomment if this is the main benchmark file and add main function.
int main(int argc, char** argv) {
  ::benchmark::Initialize(&argc, argv);
  if (::benchmark::ReportUnrecognizedArguments(argc, argv)) return 1;
  ::benchmark::RunSpecifiedBenchmarks();
  return 0;
} 