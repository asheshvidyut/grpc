/*
 * Copyright 2026 gRPC authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 */

#include "grpcio_native/handler.h"
#include "echo.pb.h"
#include <string>
#include <cstdlib>
#include <cstring>

GRPCIO_NATIVE_DECLARE_ABI()

namespace {

char* malloc_copy(const std::string& s) {
  char* buf = static_cast<char*>(std::malloc(s.size()));
  if (buf && !s.empty()) {
    std::memcpy(buf, s.data(), s.size());
  }
  return buf;
}

}  // namespace

extern "C" GRPCIO_NATIVE_EXPORT
int echo_unary(grpc_native_unary_call* call) {
  echo::EchoRequest req;
  if (!req.ParseFromArray(call->req_data, static_cast<int>(call->req_len))) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    const char* err = "Failed to parse EchoRequest";
    call->err_msg = malloc_copy(err);
    call->err_msg_len = std::strlen(err);
    return 0;
  }

  echo::EchoResponse resp;
  resp.set_message(req.message());

  std::string out;
  if (!resp.SerializeToString(&out)) {
    call->status = GRPC_NATIVE_STATUS_INTERNAL;
    const char* err = "Failed to serialize EchoResponse";
    call->err_msg = malloc_copy(err);
    call->err_msg_len = std::strlen(err);
    return 0;
  }

  call->resp_data = malloc_copy(out);
  call->resp_len = out.size();
  call->status = GRPC_NATIVE_STATUS_OK;
  return 0;
}

extern "C" GRPCIO_NATIVE_EXPORT
int echo_stream(grpc_native_unary_stream_call* call) {
  echo::EchoRequest req;
  if (!req.ParseFromArray(call->req_data, static_cast<int>(call->req_len))) {
    call->status = GRPC_NATIVE_STATUS_INVALID_ARGUMENT;
    const char* err = "Failed to parse EchoRequest";
    call->err_msg = malloc_copy(err);
    call->err_msg_len = std::strlen(err);
    return 0;
  }

  // Split message into words and stream them back!
  std::string msg = req.message();
  size_t start = 0;
  size_t end = msg.find(' ');
  while (true) {
    std::string word = msg.substr(start, end - start);
    if (!word.empty()) {
      echo::EchoResponse resp;
      resp.set_message(word);
      std::string out;
      resp.SerializeToString(&out);
      
      // Emit word response
      int rc = call->writer->emit(call->writer->ctx, out.data(), out.size());
      if (rc != 0) {
        // Stream closed or cancelled
        break;
      }
    }
    if (end == std::string::npos) {
      break;
    }
    start = end + 1;
    end = msg.find(' ', start);
  }

  call->status = GRPC_NATIVE_STATUS_OK;
  return 0;
}
