# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Build the echo native handler with protobuf C++ codegen.
#
# Requires:
#   - CMake >= 3.16
#   - protobuf (libprotobuf-dev / brew install protobuf)
#   - C++17 toolchain
#
# Build:
#   mkdir build && cd build
#   cmake ..
#   cmake --build .
#
# Then point echo_server.py at the resulting libecho_handler.{so,dylib}.

cmake_minimum_required(VERSION 3.16)
project(echo_handler CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
set(CMAKE_CXX_VISIBILITY_PRESET hidden)

find_package(Protobuf REQUIRED)
# protobuf >= 22 depends on Abseil. find_package surfaces it transitively
# only if the protobufConfig.cmake exports it; on some Homebrew installs the
# headers are needed explicitly.
find_package(absl QUIET)

set(PROTO_FILE "${CMAKE_CURRENT_SOURCE_DIR}/echo.proto")
set(PROTO_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/proto_gen")
file(MAKE_DIRECTORY "${PROTO_GEN_DIR}")

set(PROTO_SRCS "${PROTO_GEN_DIR}/echo.pb.cc")
set(PROTO_HDRS "${PROTO_GEN_DIR}/echo.pb.h")

add_custom_command(
  OUTPUT ${PROTO_SRCS} ${PROTO_HDRS}
  COMMAND protobuf::protoc
  ARGS --cpp_out "${PROTO_GEN_DIR}"
       -I "${CMAKE_CURRENT_SOURCE_DIR}"
       ${PROTO_FILE}
  DEPENDS ${PROTO_FILE}
  COMMENT "Generating C++ protobuf sources from echo.proto"
  VERBATIM
)

add_library(echo_handler SHARED
  echo_handler.cc
  ${PROTO_SRCS}
)

# Export only the C ABI symbols (and the protobuf statics it pulls in).
# Everything else is hidden by the visibility settings above.
# (No compile definitions needed — handlers tag exports via the
# GRPCIO_NATIVE_HANDLER macro from the header.)
target_include_directories(echo_handler PRIVATE
  "${CMAKE_CURRENT_SOURCE_DIR}/../../include"
  "${PROTO_GEN_DIR}"
)
target_link_libraries(echo_handler PRIVATE protobuf::libprotobuf)
if(absl_FOUND)
  # protobuf 22+ requires a broad swath of absl runtime. Link the libs that
  # contain the symbols protobuf-generated code references.
  target_link_libraries(echo_handler PRIVATE
    absl::base
    absl::strings
    absl::log_internal_check_op
    absl::log_internal_message
    absl::log_internal_nullguard
  )
endif()

# Mirror the naming convention used by the pure-C example so the same
# echo_server.py works either way.
if(APPLE)
  set_target_properties(echo_handler PROPERTIES
    PREFIX ""
    SUFFIX ".dylib"
    OUTPUT_NAME "echo_handler")
else()
  set_target_properties(echo_handler PROPERTIES
    PREFIX ""
    SUFFIX ".so"
    OUTPUT_NAME "echo_handler")
endif()
