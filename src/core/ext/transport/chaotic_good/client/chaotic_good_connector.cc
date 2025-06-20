// Copyright 2024 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include "src/core/ext/transport/chaotic_good/client/chaotic_good_connector.h"

#include <grpc/event_engine/event_engine.h>
#include <grpc/support/port_platform.h>

#include <cstdint>
#include <memory>
#include <utility>

#include "absl/log/check.h"
#include "absl/log/log.h"
#include "absl/random/bit_gen_ref.h"
#include "absl/status/status.h"
#include "absl/status/statusor.h"
#include "src/core/client_channel/client_channel_factory.h"
#include "src/core/client_channel/client_channel_filter.h"
#include "src/core/config/core_configuration.h"
#include "src/core/ext/transport/chaotic_good/chaotic_good_frame.pb.h"
#include "src/core/ext/transport/chaotic_good/client_transport.h"
#include "src/core/ext/transport/chaotic_good/frame.h"
#include "src/core/ext/transport/chaotic_good/frame_header.h"
#include "src/core/ext/transport/chaotic_good_legacy/client/chaotic_good_connector.h"
#include "src/core/handshaker/handshaker.h"
#include "src/core/handshaker/tcp_connect/tcp_connect_handshaker.h"
#include "src/core/lib/channel/channel_args.h"
#include "src/core/lib/event_engine/channel_args_endpoint_config.h"
#include "src/core/lib/event_engine/event_engine_context.h"
#include "src/core/lib/event_engine/extensions/chaotic_good_extension.h"
#include "src/core/lib/event_engine/query_extensions.h"
#include "src/core/lib/event_engine/tcp_socket_utils.h"
#include "src/core/lib/iomgr/closure.h"
#include "src/core/lib/iomgr/error.h"
#include "src/core/lib/iomgr/event_engine_shims/endpoint.h"
#include "src/core/lib/iomgr/exec_ctx.h"
#include "src/core/lib/promise/activity.h"
#include "src/core/lib/promise/all_ok.h"
#include "src/core/lib/promise/context.h"
#include "src/core/lib/promise/event_engine_wakeup_scheduler.h"
#include "src/core/lib/promise/latch.h"
#include "src/core/lib/promise/race.h"
#include "src/core/lib/promise/sleep.h"
#include "src/core/lib/promise/try_seq.h"
#include "src/core/lib/promise/wait_for_callback.h"
#include "src/core/lib/resource_quota/arena.h"
#include "src/core/lib/resource_quota/resource_quota.h"
#include "src/core/lib/slice/slice.h"
#include "src/core/lib/slice/slice_buffer.h"
#include "src/core/lib/surface/channel.h"
#include "src/core/lib/surface/channel_create.h"
#include "src/core/lib/transport/error_utils.h"
#include "src/core/lib/transport/promise_endpoint.h"
#include "src/core/telemetry/metrics.h"
#include "src/core/transport/endpoint_transport_client_channel_factory.h"
#include "src/core/util/debug_location.h"
#include "src/core/util/no_destruct.h"
#include "src/core/util/ref_counted_ptr.h"
#include "src/core/util/time.h"

using grpc_event_engine::experimental::EventEngine;

namespace grpc_core {
namespace chaotic_good {

namespace {

const int32_t kTimeoutSecs = 120;

struct ConnectPromiseEndpointResult {
  PromiseEndpoint endpoint;
  ChannelArgs channel_args;
};

using ConnectResultLatch = std::shared_ptr<
    InterActivityLatch<absl::StatusOr<ConnectPromiseEndpointResult>>>;

absl::StatusOr<ConnectPromiseEndpointResult> ResultFromHandshake(
    absl::StatusOr<HandshakerArgs*> result) {
  if (!result.ok()) {
    return result.status();
  }
  HandshakerArgs* args = *result;
  if (args->endpoint == nullptr) {
    return absl::InternalError("Handshake complete with empty endpoint.");
  }
  std::unique_ptr<grpc_event_engine::experimental::EventEngine::Endpoint>
      endpoint = grpc_event_engine::experimental::
          grpc_take_wrapped_event_engine_endpoint(
              (*result)->endpoint.release());
  if (endpoint == nullptr) {
    LOG(ERROR) << "Failed to take endpoint.";
    return absl::InternalError("Failed to take endpoint.");
  }
  auto* chaotic_good_ext = grpc_event_engine::experimental::QueryExtension<
      grpc_event_engine::experimental::ChaoticGoodExtension>(endpoint.get());
  if (chaotic_good_ext != nullptr) {
    chaotic_good_ext->EnableStatsCollection(/*is_control_channel=*/true);
    chaotic_good_ext->UseMemoryQuota(ResourceQuota::Default()->memory_quota());
  }
  return ConnectPromiseEndpointResult{
      PromiseEndpoint(std::move(endpoint), std::move(args->read_buffer)),
      args->args};
}

Promise<absl::StatusOr<ConnectPromiseEndpointResult>> ConnectPromiseEndpoint(
    EventEngine::ResolvedAddress addr, ChannelArgs channel_args,
    Timestamp deadline) {
  auto event_engine = channel_args.GetObjectRef<EventEngine>();
  auto result_latch = std::make_shared<
      InterActivityLatch<absl::StatusOr<ConnectPromiseEndpointResult>>>();
  auto handshake_mgr = MakeRefCounted<HandshakeManager>();
  absl::StatusOr<std::string> address =
      grpc_event_engine::experimental::ResolvedAddressToURI(addr);
  if (!address.ok()) {
    return Immediate<absl::StatusOr<ConnectPromiseEndpointResult>>(
        address.status());
  }
  channel_args = channel_args.Set(GRPC_ARG_TCP_HANDSHAKER_RESOLVED_ADDRESS,
                                  address.value());
  CoreConfiguration::Get().handshaker_registry().AddHandshakers(
      HandshakerType::HANDSHAKER_CLIENT, channel_args, nullptr,
      handshake_mgr.get());
  handshake_mgr->DoHandshake(
      nullptr, channel_args, deadline, nullptr /* acceptor */,
      [result_latch, handshake_mgr](absl::StatusOr<HandshakerArgs*> result) {
        result_latch->Set(ResultFromHandshake(std::move(result)));
      });
  return OnCancel(
      [result_latch, await = result_latch->Wait()]() { return await(); },
      [handshake_mgr, event_engine]() {
        handshake_mgr->Shutdown(absl::CancelledError());
      });
}

struct ConnectChaoticGoodResult {
  ConnectPromiseEndpointResult connect_result;
  chaotic_good_frame::Settings server_settings;
};

class SettingsHandshake : public RefCounted<SettingsHandshake> {
 public:
  explicit SettingsHandshake(ConnectPromiseEndpointResult connect_result)
      : connect_result_(std::move(connect_result)) {}

  auto Handshake(chaotic_good_frame::Settings client_settings) {
    SettingsFrame frame;
    frame.body = client_settings;
    SliceBuffer send_buffer;
    TcpFrameHeader{frame.MakeHeader(), 0}.Serialize(
        send_buffer.AddTiny(TcpFrameHeader::kFrameHeaderSize));
    frame.SerializePayload(send_buffer);
    return TrySeq(
        connect_result_.endpoint.Write(std::move(send_buffer),
                                       PromiseEndpoint::WriteArgs{}),
        [this]() {
          return connect_result_.endpoint.ReadSlice(
              TcpFrameHeader::kFrameHeaderSize);
        },
        [](Slice frame_header) {
          return TcpFrameHeader::Parse(frame_header.data());
        },
        [this](TcpFrameHeader frame_header) {
          if (frame_header.payload_tag != 0) {
            return absl::InternalError("Unexpected connection id in frame");
          }
          server_header_ = frame_header.header;
          return absl::OkStatus();
        },
        [this]() {
          return connect_result_.endpoint.Read(server_header_.payload_length);
        },
        [this](SliceBuffer payload) {
          return server_frame_.Deserialize(server_header_, std::move(payload));
        },
        [self = Ref()]() {
          return ConnectChaoticGoodResult{std::move(self->connect_result_),
                                          std::move(self->server_frame_.body)};
        });
  }

 private:
  ConnectPromiseEndpointResult connect_result_;
  FrameHeader server_header_;
  SettingsFrame server_frame_;
};

auto ConnectChaoticGood(EventEngine::ResolvedAddress addr,
                        const ChannelArgs& channel_args, Timestamp deadline,
                        chaotic_good_frame::Settings client_settings) {
  return TrySeq(
      ConnectPromiseEndpoint(addr, channel_args, deadline),
      [client_settings](ConnectPromiseEndpointResult connect_result) {
        return MakeRefCounted<SettingsHandshake>(std::move(connect_result))
            ->Handshake(client_settings);
      });
}

}  // namespace

void ChaoticGoodConnector::Connect(const Args& args, Result* result,
                                   grpc_closure* notify) {
  auto event_engine = args.channel_args.GetObjectRef<EventEngine>();
  auto arena = SimpleArenaAllocator(0)->MakeArena();
  auto result_notifier = std::make_unique<ResultNotifier>(args, result, notify);
  arena->SetContext(event_engine.get());
  auto resolved_addr = EventEngine::ResolvedAddress(
      reinterpret_cast<const sockaddr*>(args.address->addr), args.address->len);
  CHECK_NE(resolved_addr.address(), nullptr);
  auto* result_notifier_ptr = result_notifier.get();
  auto activity = MakeActivity(
      [result_notifier_ptr, resolved_addr]() mutable {
        chaotic_good_frame::Settings client_settings;
        client_settings.set_data_channel(false);
        result_notifier_ptr->config.PrepareClientOutgoingSettings(
            client_settings);
        return TrySeq(
            ConnectChaoticGood(
                resolved_addr, result_notifier_ptr->args.channel_args,
                Timestamp::Now() + Duration::FromSecondsAsDouble(kTimeoutSecs),
                std::move(client_settings)),
            [resolved_addr,
             result_notifier_ptr](ConnectChaoticGoodResult result) {
              auto connector = MakeRefCounted<ConnectionCreator>(
                  resolved_addr, result.connect_result.channel_args);
              auto parse_status =
                  result_notifier_ptr->config.ReceiveServerIncomingSettings(
                      result.server_settings, *connector);
              if (!parse_status.ok()) {
                return parse_status;
              }
              auto socket_node = TcpFrameTransport::MakeSocketNode(
                  result_notifier_ptr->args.channel_args,
                  result.connect_result.endpoint);
              auto frame_transport = MakeOrphanable<TcpFrameTransport>(
                  result_notifier_ptr->config.MakeTcpFrameTransportOptions(),
                  std::move(result.connect_result.endpoint),
                  result_notifier_ptr->config.TakePendingDataEndpoints(),
                  MakeRefCounted<TransportContext>(
                      result_notifier_ptr->args.channel_args,
                      std::move(socket_node)));
              auto transport = MakeOrphanable<ChaoticGoodClientTransport>(
                  result_notifier_ptr->args.channel_args,
                  std::move(frame_transport),
                  result_notifier_ptr->config.MakeMessageChunker());
              result_notifier_ptr->result->transport = transport.release();
              result_notifier_ptr->result->channel_args =
                  result.connect_result.channel_args;
              return absl::OkStatus();
            });
      },
      EventEngineWakeupScheduler(event_engine),
      [result_notifier = std::move(result_notifier)](absl::Status status) {
        result_notifier->Run(status);
      },
      arena);
  MutexLock lock(&mu_);
  if (is_shutdown_) return;
  connect_activity_ = std::move(activity);
}

PendingConnection ChaoticGoodConnector::ConnectionCreator::Connect(
    absl::string_view id) {
  chaotic_good_frame::Settings settings;
  settings.set_data_channel(true);
  settings.add_connection_id(id);
  return PendingConnection(
      id,
      Map(ConnectChaoticGood(
              address_, args_,
              Timestamp::Now() + Duration::FromSecondsAsDouble(kTimeoutSecs),
              std::move(settings)),
          [](absl::StatusOr<ConnectChaoticGoodResult> result)
              -> absl::StatusOr<PromiseEndpoint> {
            if (!result.ok()) return result.status();
            return std::move(result->connect_result.endpoint);
          }));
}

absl::StatusOr<grpc_channel*> CreateChaoticGoodChannel(
    std::string target, const ChannelArgs& args) {
  if (!IsChaoticGoodFramingLayerEnabled()) {
    return chaotic_good_legacy::CreateLegacyChaoticGoodChannel(target, args);
  }

  // Create channel.
  auto r = ChannelCreate(
      target,
      args.SetObject(
              EndpointTransportClientChannelFactory<ChaoticGoodConnector>())
          .Set(GRPC_ARG_USE_V3_STACK, true),
      GRPC_CLIENT_CHANNEL, nullptr);
  if (r.ok()) {
    return r->release()->c_ptr();
  } else {
    return r.status();
  }
}

}  // namespace chaotic_good
}  // namespace grpc_core
