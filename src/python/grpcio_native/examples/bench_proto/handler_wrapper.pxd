# Copyright 2026 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Definition file to alias protobuf type names for the JIT compiler.

from libc.stdint cimport uint32_t as uint32, uint64_t as uint64
from libcpp.string cimport string as bytes
