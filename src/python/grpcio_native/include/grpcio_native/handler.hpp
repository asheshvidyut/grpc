/*
 * Copyright 2026 gRPC authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * C++ helpers on top of the raw C ABI in handler.h.
 *
 * Writing a handler against the raw ABI requires manual ParseFromArray,
 * SerializeToString, malloc/memcpy for the response, and per-error status
 * setting. This header hides all of that behind one macro per RPC type.
 *
 * Compare:
 *
 *     // raw C ABI:
 *     GRPCIO_NATIVE_HANDLER int Rank(grpc_native_unary_call* call) {
 *       RankRequest req;
 *       if (!req.ParseFromArray(call->req_data, call->req_len)) {
 *         call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
 *         return 0;
 *       }
 *       RankResponse resp;
 *       // ... logic ...
 *       std::string wire; resp.SerializeToString(&wire);
 *       call->resp_data = (char*)std::malloc(wire.size());
 *       std::memcpy(call->resp_data, wire.data(), wire.size());
 *       call->resp_len = wire.size();
 *       return 0;
 *     }
 *
 *     // with this header:
 *     GRPCIO_NATIVE_UNARY(Rank, RankRequest, RankResponse) {
 *       // ... logic ... resp->set_X(...)
 *       return grpc::native::OK;
 *     }
 *
 * The macro generates the C-ABI entry point under the same name; the user
 * writes only typed business logic.
 */

#ifndef GRPCIO_NATIVE_HANDLER_HPP
#define GRPCIO_NATIVE_HANDLER_HPP

#include <cstdlib>
#include <cstring>
#include <string>
#include <utility>

extern "C" {
#include "grpcio_native/handler.h"
}

namespace grpc {
namespace native {

// ----------------------- Status ---------------------------------------------

class Status {
 public:
  Status() : code_(GRPC_NATIVE_STATUS_OK) {}
  Status(grpc_native_status code, std::string message = "")
      : code_(code), message_(std::move(message)) {}

  bool ok() const { return code_ == GRPC_NATIVE_STATUS_OK; }
  grpc_native_status code() const { return code_; }
  const std::string& message() const { return message_; }

 private:
  grpc_native_status code_;
  std::string message_;
};

// Inline constants and convenience factories. Use these in handler returns.
inline const Status OK;
inline Status Cancelled(std::string m = "")        { return {GRPC_NATIVE_STATUS_CANCELLED,         std::move(m)}; }
inline Status Unknown(std::string m = "")          { return {GRPC_NATIVE_STATUS_UNKNOWN,           std::move(m)}; }
inline Status InvalidArgument(std::string m = "")  { return {GRPC_NATIVE_STATUS_INVALID_ARGUMENT,  std::move(m)}; }
inline Status DeadlineExceeded(std::string m = "") { return {GRPC_NATIVE_STATUS_DEADLINE_EXCEEDED, std::move(m)}; }
inline Status NotFound(std::string m = "")         { return {GRPC_NATIVE_STATUS_NOT_FOUND,         std::move(m)}; }
inline Status AlreadyExists(std::string m = "")    { return {GRPC_NATIVE_STATUS_ALREADY_EXISTS,    std::move(m)}; }
inline Status PermissionDenied(std::string m = "") { return {GRPC_NATIVE_STATUS_PERMISSION_DENIED, std::move(m)}; }
inline Status ResourceExhausted(std::string m="")  { return {GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED,std::move(m)}; }
inline Status FailedPrecondition(std::string m="") { return {GRPC_NATIVE_STATUS_FAILED_PRECONDITION,std::move(m)}; }
inline Status Aborted(std::string m = "")          { return {GRPC_NATIVE_STATUS_ABORTED,           std::move(m)}; }
inline Status OutOfRange(std::string m = "")       { return {GRPC_NATIVE_STATUS_OUT_OF_RANGE,      std::move(m)}; }
inline Status Unimplemented(std::string m = "")    { return {GRPC_NATIVE_STATUS_UNIMPLEMENTED,     std::move(m)}; }
inline Status Internal(std::string m = "")         { return {GRPC_NATIVE_STATUS_INTERNAL,          std::move(m)}; }
inline Status Unavailable(std::string m = "")      { return {GRPC_NATIVE_STATUS_UNAVAILABLE,       std::move(m)}; }
inline Status DataLoss(std::string m = "")         { return {GRPC_NATIVE_STATUS_DATA_LOSS,         std::move(m)}; }
inline Status Unauthenticated(std::string m = "")  { return {GRPC_NATIVE_STATUS_UNAUTHENTICATED,   std::move(m)}; }

// ----------------------- Reader / Writer ------------------------------------

// Templated wrappers that parse/serialize protobuf messages on each read/write.
// Requires that T implements ParseFromArray() / SerializeToString() — true for
// all protobuf-generated types.

template <typename T>
class Reader {
 public:
  explicit Reader(grpc_native_reader* r) : r_(r) {}

  // Reads the next message into *msg. Returns true on success, false at
  // end-of-stream, peer-cancellation, or parse failure.
  bool Read(T* msg) {
    const char* data = nullptr;
    size_t len = 0;
    int rc = r_->read(r_->ctx, &data, &len);
    if (rc <= 0) return false;
    return msg->ParseFromArray(data, static_cast<int>(len));
  }

 private:
  grpc_native_reader* r_;
};

template <typename T>
class Writer {
 public:
  explicit Writer(grpc_native_writer* w) : w_(w) {}

  // Writes a message. Returns true if accepted, false if the peer has closed
  // the stream (handler should return promptly).
  bool Write(const T& msg) {
    std::string wire;
    if (!msg.SerializeToString(&wire)) return false;
    return w_->emit(w_->ctx, wire.data(), wire.size()) == 0;
  }

 private:
  grpc_native_writer* w_;
};

// ----------------------- Dispatch internals --------------------------------

namespace detail {

// Copies a std::string into a malloc'd buffer the dispatcher will free().
inline bool SetMallocBytes(char** out_data, size_t* out_len,
                            const std::string& s) {
  if (s.empty()) {
    *out_data = nullptr;
    *out_len = 0;
    return true;
  }
  char* buf = static_cast<char*>(std::malloc(s.size()));
  if (buf == nullptr) return false;
  std::memcpy(buf, s.data(), s.size());
  *out_data = buf;
  *out_len = s.size();
  return true;
}

inline void ApplyError(grpc_native_status* status_field, char** err_msg_out,
                       size_t* err_len_out, const Status& s) {
  *status_field = s.code();
  if (!s.message().empty()) {
    if (!SetMallocBytes(err_msg_out, err_len_out, s.message())) {
      *err_msg_out = nullptr;
      *err_len_out = 0;
    }
  }
}

template <typename Req, typename Resp, typename Fn>
int DispatchUnary(grpc_native_unary_call* call, Fn fn) {
  Req req;
  if (!req.ParseFromArray(call->req_data,
                          static_cast<int>(call->req_len))) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               InvalidArgument("failed to parse request"));
    return 0;
  }
  Resp resp;
  Status s = fn(req, &resp);
  if (!s.ok()) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len, s);
    return 0;
  }
  std::string wire;
  if (!resp.SerializeToString(&wire)) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               Internal("failed to serialize response"));
    return 0;
  }
  if (!SetMallocBytes(&call->resp_data, &call->resp_len, wire)) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               ResourceExhausted("out of memory"));
    return 0;
  }
  return 0;
}

template <typename Req, typename Resp, typename Fn>
int DispatchUnaryStream(grpc_native_unary_stream_call* call, Fn fn) {
  Req req;
  if (!req.ParseFromArray(call->req_data,
                          static_cast<int>(call->req_len))) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               InvalidArgument("failed to parse request"));
    return 0;
  }
  Writer<Resp> writer(call->writer);
  Status s = fn(req, writer);
  if (!s.ok()) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len, s);
  }
  return 0;
}

template <typename Req, typename Resp, typename Fn>
int DispatchStreamUnary(grpc_native_stream_unary_call* call, Fn fn) {
  Reader<Req> reader(call->reader);
  Resp resp;
  Status s = fn(reader, &resp);
  if (!s.ok()) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len, s);
    return 0;
  }
  std::string wire;
  if (!resp.SerializeToString(&wire)) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               Internal("failed to serialize response"));
    return 0;
  }
  if (!SetMallocBytes(&call->resp_data, &call->resp_len, wire)) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len,
               ResourceExhausted("out of memory"));
    return 0;
  }
  return 0;
}

template <typename Req, typename Resp, typename Fn>
int DispatchStreamStream(grpc_native_stream_stream_call* call, Fn fn) {
  Reader<Req> reader(call->reader);
  Writer<Resp> writer(call->writer);
  Status s = fn(reader, writer);
  if (!s.ok()) {
    ApplyError(&call->status, &call->err_msg, &call->err_msg_len, s);
  }
  return 0;
}

}  // namespace detail

}  // namespace native
}  // namespace grpc

// ----------------------- User-facing macros --------------------------------
//
// Each macro generates:
//   1. A forward declaration of the typed implementation function
//   2. An extern "C" C-ABI entry point with the user-supplied symbol name
//   3. The opening of the typed implementation, ready for the user's body
//
// The user writes:
//
//   GRPCIO_NATIVE_UNARY(Rank, RankRequest, RankResponse) {
//     // body — `req` is const RankRequest&, `resp` is RankResponse*
//     return grpc::native::OK;
//   }

#define GRPCIO_NATIVE_UNARY(name, RequestT, ResponseT)                       \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      const RequestT& req, ResponseT* resp);                                 \
  extern "C" GRPCIO_NATIVE_HANDLER int name(grpc_native_unary_call* call) {  \
    return ::grpc::native::detail::DispatchUnary<RequestT, ResponseT>(       \
        call, &_grpcio_native_##name##_impl);                                \
  }                                                                          \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      const RequestT& req, ResponseT* resp)

#define GRPCIO_NATIVE_UNARY_STREAM(name, RequestT, ResponseT)                \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      const RequestT& req, ::grpc::native::Writer<ResponseT>& writer);       \
  extern "C" GRPCIO_NATIVE_HANDLER int name(                                 \
      grpc_native_unary_stream_call* call) {                                 \
    return ::grpc::native::detail::DispatchUnaryStream<                      \
        RequestT, ResponseT>(call, &_grpcio_native_##name##_impl);           \
  }                                                                          \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      const RequestT& req, ::grpc::native::Writer<ResponseT>& writer)

#define GRPCIO_NATIVE_STREAM_UNARY(name, RequestT, ResponseT)                \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      ::grpc::native::Reader<RequestT>& reader, ResponseT* resp);            \
  extern "C" GRPCIO_NATIVE_HANDLER int name(                                 \
      grpc_native_stream_unary_call* call) {                                 \
    return ::grpc::native::detail::DispatchStreamUnary<                      \
        RequestT, ResponseT>(call, &_grpcio_native_##name##_impl);           \
  }                                                                          \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      ::grpc::native::Reader<RequestT>& reader, ResponseT* resp)

#define GRPCIO_NATIVE_STREAM_STREAM(name, RequestT, ResponseT)               \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      ::grpc::native::Reader<RequestT>& reader,                              \
      ::grpc::native::Writer<ResponseT>& writer);                            \
  extern "C" GRPCIO_NATIVE_HANDLER int name(                                 \
      grpc_native_stream_stream_call* call) {                                \
    return ::grpc::native::detail::DispatchStreamStream<                     \
        RequestT, ResponseT>(call, &_grpcio_native_##name##_impl);           \
  }                                                                          \
  static ::grpc::native::Status _grpcio_native_##name##_impl(                \
      ::grpc::native::Reader<RequestT>& reader,                              \
      ::grpc::native::Writer<ResponseT>& writer)

#endif  // GRPCIO_NATIVE_HANDLER_HPP
