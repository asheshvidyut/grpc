# Copyright 2019 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from tests import _loader
from tests import _runner
import multiprocessing
import sys
if sys.platform == "darwin":
    try:
        multiprocessing.set_start_method("fork", force=True)
    except RuntimeError:
        pass

from grpc.experimental import aio
_original_aio_server = aio.server
def _aio_server(*args, **kwargs):
    options = kwargs.get('options', None)
    options = list(options) if options else []
    if not any(k == 'grpc.so_reuseport' for k, v in options):
        options.append(('grpc.so_reuseport', 0))
    kwargs['options'] = tuple(options)
    return _original_aio_server(*args, **kwargs)
aio.server = _aio_server

Loader = _loader.Loader
Runner = _runner.Runner
