#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <thread>
#include <vector>

#include <gtest/gtest.h>
#include <grpc/event_engine/event_engine.h>
#include <grpc/grpc.h>
#include <grpc/support/log.h>

#include "src/core/lib/surface/init.h"
#include "test/core/test_util/test_config.h"

using grpc_event_engine::experimental::EventEngine;
using grpc_event_engine::experimental::GetDefaultEventEngine;

namespace {

void AnswerSingleDnsQuery(int fd) {
  uint8_t buf[512];
  sockaddr_in client_addr{};
  socklen_t addr_len = sizeof(client_addr);
  ssize_t n = recvfrom(fd, buf, sizeof(buf), 0,
                       reinterpret_cast<sockaddr*>(&client_addr), &addr_len);
  ASSERT_GT(n, 12);

  // Construct DNS response header matching query transaction ID (buf[0], buf[1])
  std::vector<uint8_t> resp;
  resp.push_back(buf[0]);
  resp.push_back(buf[1]);  // Transaction ID
  resp.push_back(0x84);
  resp.push_back(0x00);    // Flags: Response, Authoritative, No Error
  resp.push_back(0x00);
  resp.push_back(0x01);    // QDCOUNT: 1
  resp.push_back(0x00);
  resp.push_back(0x01);    // ANCOUNT: 1
  resp.push_back(0x00);
  resp.push_back(0x00);    // NSCOUNT: 0
  resp.push_back(0x00);
  resp.push_back(0x00);    // ARCOUNT: 0

  // Copy Question section from query (buf[12...n])
  resp.insert(resp.end(), buf + 12, buf + n);

  // Answer section: Pointer to QNAME (0xC00C), Type A (1), Class IN (1),
  // TTL (2000), RDLENGTH (4), RDATA (1.2.3.4)
  const uint8_t answer_tail[] = {0xC0, 0x0C, 0x00, 0x01, 0x00, 0x01,
                                 0x00, 0x00, 0x07, 0xD0, 0x00, 0x04,
                                 1,    2,    3,    4};
  resp.insert(resp.end(), std::begin(answer_tail), std::end(answer_tail));

  sendto(fd, resp.data(), resp.size(), 0,
         reinterpret_cast<sockaddr*>(&client_addr), addr_len);
}

}  // namespace

TEST(DnsShutdownCrashTest, ReproRaceCondition) {
  grpc_init();

  {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    ASSERT_GE(fd, 0);

    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = 0;  // Ephemeral port
    server_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    ASSERT_EQ(bind(fd, reinterpret_cast<sockaddr*>(&server_addr),
                   sizeof(server_addr)),
              0);

    socklen_t len = sizeof(server_addr);
    ASSERT_EQ(getsockname(fd, reinterpret_cast<sockaddr*>(&server_addr), &len),
              0);
    int port = ntohs(server_addr.sin_port);
    std::string dns_server_addr = "127.0.0.1:" + std::to_string(port);

    auto ee = GetDefaultEventEngine();
    auto resolver_status = ee->GetDNSResolver({dns_server_addr});
    ASSERT_TRUE(resolver_status.ok()) << resolver_status.status();
    auto resolver = std::move(*resolver_status);

    // Initiate dual-stack lookup (pending_requests = 2) for a non-localhost name
    // so that c-ares must send network DNS queries.
    resolver->LookupHostname(
        [](absl::StatusOr<std::vector<EventEngine::ResolvedAddress>> /*res*/) {
          // Callback running asynchronously on an EventEngine thread
        },
        "testdomain.test", "80");

    // Answer only the first query (A or AAAA), leaving the second query pending
    AnswerSingleDnsQuery(fd);

    // Sleep briefly so that c-ares receives and processes the answer,
    // populating hostname_qa->result while the second query is still pending.
    std::this_thread::sleep_for(std::chrono::milliseconds(20));

    // Close socket so no more queries can be answered
    close(fd);

    // Initiate gRPC shutdown -> calls address_sorting_shutdown() ->
    // sets g_current_source_addr_factory = NULL.
    grpc_shutdown();

    // Destruction/cancellation of resolver triggers OnHostbynameDoneLocked()
    // with ARES_ECANCELLED on the remaining query, which calls
    // SortAddresses(result) and crashes.
  }
}

int main(int argc, char** argv) {
  grpc::testing::TestEnvironment env(&argc, argv);
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}

