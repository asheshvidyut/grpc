# Copyright 2017 gRPC authors.
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

import collections


class InitialMetadataFlags:
  used_mask = GRPC_INITIAL_METADATA_USED_MASK
  wait_for_ready = GRPC_INITIAL_METADATA_WAIT_FOR_READY
  wait_for_ready_explicitly_set = GRPC_INITIAL_METADATA_WAIT_FOR_READY_EXPLICITLY_SET


_Metadatum = collections.namedtuple('_Metadatum', ('key', 'value',))


cdef void _store_c_metadata(
    metadata, grpc_metadata **c_metadata, size_t *c_count) except *:
  cdef size_t metadatum_count
  cdef size_t index
  cdef object key
  cdef object value
  cdef bytes encoded_key
  cdef object encoded_value
  cdef const unsigned char[::1] view

  if metadata is None:
    c_count[0] = 0
    c_metadata[0] = NULL
  else:
    metadatum_count = len(metadata)
    if metadatum_count == 0:
      c_count[0] = 0
      c_metadata[0] = NULL
    else:
      c_count[0] = metadatum_count
      c_metadata[0] = <grpc_metadata *>gpr_malloc(
          metadatum_count * sizeof(grpc_metadata))
      for index, (key, value) in enumerate(metadata):
        encoded_key = _encode(key)
        encoded_value = value if encoded_key[-4:] == b'-bin' else _encode(value)
        if not isinstance(encoded_value, bytes):
          raise TypeError('Binary metadata key="%s" expected bytes, got %s' % (
            key,
            type(encoded_value)
          ))
        c_metadata[0][index].key = _slice_from_bytes(encoded_key)
        
        view = encoded_value
        if view.shape[0] > 0:
          Py_INCREF(encoded_value)
          c_metadata[0][index].value = grpc_slice_new_with_user_data(
              <void*>&view[0], view.shape[0], py_decref_destroy, <void*>encoded_value)
        else:
          c_metadata[0][index].value = grpc_empty_slice()


cdef void _release_c_metadata(grpc_metadata *c_metadata, int count) except *:
  if 0 < count:
    for index in range(count):
      grpc_slice_unref(c_metadata[index].key)
      grpc_slice_unref(c_metadata[index].value)
    gpr_free(c_metadata)


cdef tuple _metadatum(grpc_slice key_slice, grpc_slice value_slice):
  cdef bytes key = _slice_bytes(key_slice)
  cdef GrpcSliceView view
  if key[-4:] == b'-bin':
    view = GrpcSliceView()
    view.set_slice(value_slice)
    return <tuple>_Metadatum(_decode(key), memoryview(view))
  else:
    return <tuple>_Metadatum(_decode(key), _decode(_slice_bytes(value_slice)))


cdef tuple _metadata(grpc_metadata_array *c_metadata_array):
  return tuple(
      _metadatum(
          c_metadata_array.metadata[index].key,
          c_metadata_array.metadata[index].value)
      for index in range(c_metadata_array.count))
