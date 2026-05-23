// Copyright 2026 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Production-shape example of a grpcio_native handler using the C++ helper
// header. The macros below expand to the raw C ABI entry point; the user
// writes typed business logic only — no manual parse/serialize/malloc.

#include "grpcio_native/handler.hpp"
#include "echo.pb.h"

GRPCIO_NATIVE_DECLARE_ABI()

GRPCIO_NATIVE_UNARY(Echo, echo::EchoRequest, echo::EchoResponse) {
  int repeat = req.repeat();
  if (repeat < 0 || repeat > 1024) {
    return grpc::native::InvalidArgument("repeat out of range [0, 1024]");
  }

  std::string& out = *resp->mutable_message();
  out.reserve(req.message().size() * repeat);
  for (int i = 0; i < repeat; ++i) {
    out.append(req.message());
  }
  return grpc::native::OK;
}
