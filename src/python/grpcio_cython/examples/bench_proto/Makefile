# Build the shared library for the three-way benchmark.
#
# Requires: protoc, libprotobuf (e.g. `brew install protobuf` on macOS), a
# C++17 compiler, and the grpcio_cython header in ../../include/.

UNAME := $(shell uname)

ifeq ($(UNAME),Darwin)
  LIBEXT = dylib
  PLATFORM_FLAGS = -undefined dynamic_lookup
else
  LIBEXT = so
  PLATFORM_FLAGS =
endif

CXX ?= c++
PROTOC ?= protoc

INCLUDES = -I. -I../../include $(shell pkg-config --cflags protobuf 2>/dev/null)
LIBS = $(shell pkg-config --libs protobuf 2>/dev/null || echo "-lprotobuf")

CXXFLAGS = -O3 -std=c++17 -fPIC -fvisibility=hidden -Wall $(INCLUDES)
LDFLAGS = -shared $(PLATFORM_FLAGS)

TARGET = bench_handler.$(LIBEXT)
PROTO_CC = bench.pb.cc
PROTO_H = bench.pb.h
PROTO_PY = bench_pb2.py
PROTO_GRPC_PY = bench_pb2_grpc.py

.PHONY: all clean

all: $(TARGET) $(PROTO_PY) $(PROTO_GRPC_PY)

$(TARGET): bench_handler.cpp
	$(CXX) $(CXXFLAGS) -DNO_PROTO_BINDINGS $(LDFLAGS) bench_handler.cpp -o $@

$(PROTO_CC) $(PROTO_H): bench.proto
	$(PROTOC) --cpp_out=. bench.proto

$(PROTO_PY) $(PROTO_GRPC_PY): bench.proto
	python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. bench.proto

clean:
	rm -f $(TARGET) $(PROTO_CC) $(PROTO_H) $(PROTO_PY) $(PROTO_GRPC_PY)
