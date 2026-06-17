/*
 * Copyright 2026 gRPC authors.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 */

#ifndef GRPCIO_NATIVE_HANDLER_H
#define GRPCIO_NATIVE_HANDLER_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Symbol visibility: native handlers must export their entry points. When
 * the user builds with -fvisibility=hidden (common for shared libraries),
 * this macro restores default visibility for the symbols the dispatcher
 * looks up by name. */
#if defined(_WIN32)
#define GRPCIO_NATIVE_EXPORT __declspec(dllexport)
#else
#define GRPCIO_NATIVE_EXPORT __attribute__((visibility("default")))
#endif

/*
 * The native handler ABI.
 *
 * A native handler is a C-linkage function exported from a shared library that
 * gRPC Python invokes to service an RPC method, bypassing the Python handler
 * path. The grpcio_cython dispatcher calls the function with the Python GIL
 * released, so the handler must not touch the CPython API.
 *
 * Memory ownership:
 *   - Request bytes (req_data) are owned by the dispatcher and remain valid
 *     for the duration of the call. The handler MUST NOT free them.
 *   - The handler writes the response by calling resp_alloc(resp_ctx, n) to
 *     obtain an n-byte buffer owned by the dispatcher, then filling it. The
 *     handler MUST NOT free that buffer; the dispatcher reclaims it after
 *     transmission.
 *   - For an error status, the handler returns a non-zero grpc status code
 *     and may call err_set(err_ctx, msg, msg_len) to attach error details.
 *
 * Threading:
 *   - Multiple invocations may run concurrently from different OS threads.
 *   - The handler must be thread-safe.
 *
 * ABI versioning:
 *   - GRPCIO_NATIVE_ABI_VERSION is bumped on incompatible changes.
 *   - The loader checks the version exported by the .so via the symbol
 *     grpcio_cython_abi_version(). A mismatch is a load-time error.
 */

#define GRPCIO_NATIVE_ABI_VERSION 3

/* gRPC status codes mirrored here so user handlers don't need to depend on
 * grpc/status.h. Values match include/grpc/impl/codegen/status.h. */
typedef enum {
  GRPC_NATIVE_STATUS_OK = 0,
  GRPC_NATIVE_STATUS_CANCELLED = 1,
  GRPC_NATIVE_STATUS_UNKNOWN = 2,
  GRPC_NATIVE_STATUS_INVALID_ARGUMENT = 3,
  GRPC_NATIVE_STATUS_DEADLINE_EXCEEDED = 4,
  GRPC_NATIVE_STATUS_NOT_FOUND = 5,
  GRPC_NATIVE_STATUS_ALREADY_EXISTS = 6,
  GRPC_NATIVE_STATUS_PERMISSION_DENIED = 7,
  GRPC_NATIVE_STATUS_RESOURCE_EXHAUSTED = 8,
  GRPC_NATIVE_STATUS_FAILED_PRECONDITION = 9,
  GRPC_NATIVE_STATUS_ABORTED = 10,
  GRPC_NATIVE_STATUS_OUT_OF_RANGE = 11,
  GRPC_NATIVE_STATUS_UNIMPLEMENTED = 12,
  GRPC_NATIVE_STATUS_INTERNAL = 13,
  GRPC_NATIVE_STATUS_UNAVAILABLE = 14,
  GRPC_NATIVE_STATUS_DATA_LOSS = 15,
  GRPC_NATIVE_STATUS_UNAUTHENTICATED = 16
} grpc_native_status;

/*
 * grpc_native_context
 *
 * Carries RPC-level information from the dispatcher to the handler:
 * cancellation status, request metadata, response trailers, deadline, and
 * peer identity. All accessors are safe to call from the handler thread
 * with the GIL released.
 *
 * Lifetime: the context is valid for the duration of the handler call. The
 * dispatcher owns it and frees it after the handler returns.
 *
 * Strings returned by get_metadata/peer are owned by the dispatcher. They
 * remain valid until the next call to the same accessor or the end of the
 * handler — whichever comes first. The handler must copy if it needs the
 * value longer.
 */
typedef struct grpc_native_context {
  void* ctx;

  /* Returns non-zero if the RPC has been cancelled (client hung up, deadline
   * exceeded, etc.). Long-running handlers should poll this periodically and
   * return early when it becomes true. */
  int (*is_cancelled)(void* ctx);

  /* Looks up a metadata value by key (binary metadata supported by using
   * '-bin' suffix in the key, same as gRPC convention).
   *
   * Returns 1 if found (*value / *len set), 0 if not found.
   * The pointer in *value is valid until the next get_metadata call. */
  int (*get_metadata)(void* ctx, const char* key,
                      const char** value, size_t* len);

  /* Sets one entry in the response trailing metadata. Successive calls
   * accumulate. Returns 0 on success.
   *
   * The dispatcher copies key/value, so the handler may free them
   * immediately. */
  int (*set_trailing_metadata)(void* ctx, const char* key,
                               const char* value, size_t len);

  /* Time remaining until the RPC deadline, in nanoseconds. Returns INT64_MAX
   * if no deadline was set. */
  int64_t (*time_remaining_ns)(void* ctx);

  /* Peer identity (typically IP:port or similar). Returned pointer is
   * NUL-terminated and valid until the handler returns. NULL if not
   * available. */
  const char* (*peer)(void* ctx);
} grpc_native_context;

/*
 * grpc_native_unary_call_t
 *
 * The handler fills in response bytes and an optional error.
 *
 * Fields (set by dispatcher before the call):
 *   req_data, req_len     : request bytes (read-only)
 *
 * Fields (set by handler):
 *   resp_data, resp_len   : response bytes; allocated by the handler with
 *                           malloc(). The dispatcher takes ownership and will
 *                           free() the buffer after transmission.
 *   status                : final gRPC status code. Defaults to OK.
 *   err_msg, err_msg_len  : optional error message; allocated by handler with
 *                           malloc(); dispatcher frees. Only meaningful when
 *                           status != OK.
 */
typedef struct {
  /* In: RPC context (cancellation, metadata, deadline, peer). */
  grpc_native_context* context;

  /* In: request payload (read-only, dispatcher-owned). */
  const char* req_data;
  size_t req_len;

  /* Out: response payload (handler-allocated, dispatcher-freed). */
  char* resp_data;
  size_t resp_len;

  /* Out: status. Defaults to OK (0). */
  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_unary_call;

/*
 * Unary-unary handler entry point.
 *
 * Return value: 0 on success, non-zero on fatal/unexpected failure (in which
 * case the dispatcher converts to INTERNAL status). For application errors,
 * set call->status and return 0.
 */
typedef int (*grpc_native_unary_unary_fn)(grpc_native_unary_call* call);

/*
 * Streaming response writer.
 *
 * For server-streaming and bidi RPCs the handler emits messages by repeatedly
 * calling writer->emit(writer->ctx, data, len). emit() copies the bytes (so
 * the handler may reuse its buffer immediately) and returns 0 on success or
 * non-zero if the stream is closed/cancelled.
 */
typedef struct grpc_native_writer {
  void* ctx;
  int (*emit)(void* ctx, const char* data, size_t len);
} grpc_native_writer;

typedef struct {
  grpc_native_context* context;
  const char* req_data;
  size_t req_len;
  grpc_native_writer* writer;

  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_unary_stream_call;

typedef int (*grpc_native_unary_stream_fn)(grpc_native_unary_stream_call* call);

/*
 * Streaming request reader.
 *
 * For client-streaming and bidi RPCs the handler pulls request messages by
 * repeatedly calling reader->read(reader->ctx, &out_data, &out_len).
 *
 * Return value:
 *    1: a message was read; *out_data / *out_len point to bytes owned by the
 *       dispatcher. The pointers are valid until the next call to read() or
 *       until the handler returns, whichever comes first. The handler must
 *       copy the bytes if it needs them longer.
 *    0: end-of-stream; the client has sent all of its messages.
 *   -1: error (client cancelled, deadline exceeded, transport closed). The
 *       handler should clean up and return.
 */
typedef struct grpc_native_reader {
  void* ctx;
  int (*read)(void* ctx, const char** out_data, size_t* out_len);
} grpc_native_reader;

/* Stream-unary: client streams requests, server returns single response. */
typedef struct {
  grpc_native_context* context;
  grpc_native_reader* reader;

  /* Out: response payload (handler-allocated, dispatcher-freed). */
  char* resp_data;
  size_t resp_len;

  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_stream_unary_call;

typedef int (*grpc_native_stream_unary_fn)(grpc_native_stream_unary_call* call);

/* Stream-stream: bidirectional. */
typedef struct {
  grpc_native_context* context;
  grpc_native_reader* reader;
  grpc_native_writer* writer;

  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_stream_stream_call;

typedef int (*grpc_native_stream_stream_fn)(grpc_native_stream_stream_call* call);

/*
 * Module-level exports the loader looks up by name when opening a .so:
 *
 *   uint32_t grpcio_cython_abi_version(void);
 *
 * Returns GRPCIO_NATIVE_ABI_VERSION at the time the .so was built. The loader
 * checks this matches the version expected by the running grpcio_cython
 * Python package. If it doesn't, loading fails.
 */
typedef uint32_t (*grpcio_cython_abi_version_fn)(void);

/* Convenience macro for handlers to export their ABI version. Wraps in
 * extern "C" so the symbol has C linkage even when used in a .cc file. */
#ifdef __cplusplus
#define GRPCIO_NATIVE_DECLARE_ABI()                                  \
  extern "C" GRPCIO_NATIVE_EXPORT uint32_t                           \
  grpcio_cython_abi_version(void) {                                  \
    return GRPCIO_NATIVE_ABI_VERSION;                                \
  }
#else
#define GRPCIO_NATIVE_DECLARE_ABI()                                  \
  GRPCIO_NATIVE_EXPORT uint32_t grpcio_cython_abi_version(void) {    \
    return GRPCIO_NATIVE_ABI_VERSION;                                \
  }
#endif

/* Convenience macro for declaring an exported handler symbol. The user can
 * use this prefix on their function definitions to ensure they're visible. */
#define GRPCIO_NATIVE_HANDLER GRPCIO_NATIVE_EXPORT

/* ---- Client Fast-Path ABI ---- */

typedef struct {
  const char* method;
  const char* req_data;
  size_t req_len;
  char* resp_data;
  size_t resp_len;
  grpc_native_status status;
  char* err_msg;
  size_t err_msg_len;
} grpc_native_client_call;

typedef int (*grpcio_cython_invoke_fn)(
    void* c_channel,
    grpc_native_client_call* call,
    int64_t timeout_ms
);

#ifdef __cplusplus
}  /* extern "C" */
#endif

#endif  /* GRPCIO_NATIVE_HANDLER_H */
