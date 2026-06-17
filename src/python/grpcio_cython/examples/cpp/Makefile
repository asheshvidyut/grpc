# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

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

TARGET = echo_handler.$(LIBEXT)
PROTO_CC = echo.pb.cc
PROTO_H = echo.pb.h
PROTO_PY = echo_pb2.py
PROTO_GRPC_PY = echo_pb2_grpc.py

.PHONY: all clean

all: $(TARGET)

$(TARGET): echo_handler.cpp $(PROTO_CC) $(PROTO_H)
	$(CXX) $(CXXFLAGS) $(LDFLAGS) echo_handler.cpp $(PROTO_CC) -o $@ $(LIBS)

$(PROTO_CC) $(PROTO_H): echo.proto
	$(PROTOC) --cpp_out=. echo.proto

clean:
	rm -f $(TARGET) $(PROTO_CC) $(PROTO_H) $(PROTO_PY) $(PROTO_GRPC_PY)
