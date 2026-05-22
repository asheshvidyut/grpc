//
//
// Copyright 2015 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
//

#include "src/core/ext/transport/chttp2/transport/bin_encoder.h"

#include <grpc/support/port_platform.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "src/core/ext/transport/chttp2/transport/huffsyms.h"
#include "src/core/ext/transport/chttp2/transport/simd_dispatch.h"
#include "src/core/util/grpc_check.h"

#if defined(__x86_64__) || defined(_M_X64)
#include <immintrin.h>
#define GRPC_SIMD_BASE64_X86 1
#define GRPC_SIMD_HUFFMAN_X86 1
#if defined(__GNUC__) || defined(__clang__)
#define GRPC_SIMD_TARGET_SSE41 __attribute__((target("sse4.1")))
#define GRPC_SIMD_TARGET_AVX2 __attribute__((target("avx2")))
#else
#define GRPC_SIMD_TARGET_SSE41
#define GRPC_SIMD_TARGET_AVX2
#endif
#endif

static const char alphabet[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

struct b64_huff_sym {
  uint16_t bits;
  uint8_t length;
};
static const b64_huff_sym huff_alphabet[64] = {
    {0x21, 6}, {0x5d, 7}, {0x5e, 7},   {0x5f, 7}, {0x60, 7}, {0x61, 7},
    {0x62, 7}, {0x63, 7}, {0x64, 7},   {0x65, 7}, {0x66, 7}, {0x67, 7},
    {0x68, 7}, {0x69, 7}, {0x6a, 7},   {0x6b, 7}, {0x6c, 7}, {0x6d, 7},
    {0x6e, 7}, {0x6f, 7}, {0x70, 7},   {0x71, 7}, {0x72, 7}, {0xfc, 8},
    {0x73, 7}, {0xfd, 8}, {0x3, 5},    {0x23, 6}, {0x4, 5},  {0x24, 6},
    {0x5, 5},  {0x25, 6}, {0x26, 6},   {0x27, 6}, {0x6, 5},  {0x74, 7},
    {0x75, 7}, {0x28, 6}, {0x29, 6},   {0x2a, 6}, {0x7, 5},  {0x2b, 6},
    {0x76, 7}, {0x2c, 6}, {0x8, 5},    {0x9, 5},  {0x2d, 6}, {0x77, 7},
    {0x78, 7}, {0x79, 7}, {0x7a, 7},   {0x7b, 7}, {0x0, 5},  {0x1, 5},
    {0x2, 5},  {0x19, 6}, {0x1a, 6},   {0x1b, 6}, {0x1c, 6}, {0x1d, 6},
    {0x1e, 6}, {0x1f, 6}, {0x7fb, 11}, {0x18, 6}};

static const uint8_t tail_xtra[3] = {0, 2, 3};

#ifdef GRPC_SIMD_BASE64_X86
namespace {

// SSE4.1 base64 encode chunk: consumes 12 input bytes and writes 16 ASCII
// output bytes. Loads 16 bytes from `in` (4 trailing bytes loaded but not
// used); the caller must ensure those 4 bytes are readable. Algorithm is the
// canonical Lemire/aklomp shuffle+mul technique; see
// https://arxiv.org/abs/1704.00605.
GRPC_SIMD_TARGET_SSE41
inline void base64_encode_chunk_sse41(const uint8_t* in, char* out) {
  __m128i input = _mm_loadu_si128(reinterpret_cast<const __m128i*>(in));

  // Reshuffle: each 32-bit lane gets [b1 b0 b2 b1] from its source triplet,
  // arranging the bytes so the four 6-bit groups can be extracted with
  // independent multiplies on 16-bit halves.
  const __m128i shuf =
      _mm_set_epi8(10, 11, 9, 10, 7, 8, 6, 7, 4, 5, 3, 4, 1, 2, 0, 1);
  input = _mm_shuffle_epi8(input, shuf);

  // Extract the four 6-bit indices per 32-bit lane.
  const __m128i t0 = _mm_and_si128(input, _mm_set1_epi32(0x0fc0fc00));
  const __m128i t1 = _mm_mulhi_epu16(t0, _mm_set1_epi32(0x04000040));
  const __m128i t2 = _mm_and_si128(input, _mm_set1_epi32(0x003f03f0));
  const __m128i t3 = _mm_mullo_epi16(t2, _mm_set1_epi32(0x01000010));
  __m128i indices = _mm_or_si128(t1, t3);

  // Classify each 6-bit index into one of 5 ranges and add the right offset
  // to produce the standard base64 ASCII character.
  const __m128i lut = _mm_setr_epi8(65, 71, -4, -4, -4, -4, -4, -4, -4, -4, -4,
                                    -4, -19, -16, 0, 0);
  __m128i sel = _mm_subs_epu8(indices, _mm_set1_epi8(51));
  __m128i mask = _mm_cmpgt_epi8(indices, _mm_set1_epi8(25));
  sel = _mm_sub_epi8(sel, mask);
  __m128i translated = _mm_shuffle_epi8(lut, sel);
  __m128i encoded = _mm_add_epi8(indices, translated);

  _mm_storeu_si128(reinterpret_cast<__m128i*>(out), encoded);
}

}  // namespace
#endif  // GRPC_SIMD_BASE64_X86

grpc_slice grpc_chttp2_base64_encode(const grpc_slice& input) {
  size_t input_length = GRPC_SLICE_LENGTH(input);
  size_t input_triplets = input_length / 3;
  size_t tail_case = input_length % 3;
  size_t output_length = (input_triplets * 4) + tail_xtra[tail_case];
  grpc_slice output = GRPC_SLICE_MALLOC(output_length);
  const uint8_t* in = GRPC_SLICE_START_PTR(input);
  const uint8_t* in_end = GRPC_SLICE_END_PTR(input);
  char* out = reinterpret_cast<char*> GRPC_SLICE_START_PTR(output);
  size_t i;

#ifdef GRPC_SIMD_BASE64_X86
  // SIMD fast path (gated on env var GRPC_SIMD_ACCELERATION + runtime CPU
  // detection). Each chunk consumes 12 input bytes and emits 16 ASCII bytes
  // but reads 16 input bytes, so we only enter while ≥16 bytes remain.
  if (grpc_core::simd::UseSse41()) {
    while (input_triplets >= 4 && in + 16 <= in_end) {
      base64_encode_chunk_sse41(in, out);
      in += 12;
      out += 16;
      input_triplets -= 4;
    }
  }
#endif

  // encode full triplets
  for (i = 0; i < input_triplets; i++) {
    out[0] = alphabet[in[0] >> 2];
    out[1] = alphabet[((in[0] & 0x3) << 4) | (in[1] >> 4)];
    out[2] = alphabet[((in[1] & 0xf) << 2) | (in[2] >> 6)];
    out[3] = alphabet[in[2] & 0x3f];
    out += 4;
    in += 3;
  }

  // encode the remaining bytes
  switch (tail_case) {
    case 0:
      break;
    case 1:
      out[0] = alphabet[in[0] >> 2];
      out[1] = alphabet[(in[0] & 0x3) << 4];
      out += 2;
      in += 1;
      break;
    case 2:
      out[0] = alphabet[in[0] >> 2];
      out[1] = alphabet[((in[0] & 0x3) << 4) | (in[1] >> 4)];
      out[2] = alphabet[(in[1] & 0xf) << 2];
      out += 3;
      in += 2;
      break;
  }

  GRPC_CHECK(out == (char*)GRPC_SLICE_END_PTR(output));
  GRPC_CHECK(in == GRPC_SLICE_END_PTR(input));
  return output;
}

#ifdef GRPC_SIMD_HUFFMAN_X86
namespace {

// AVX2 first-pass length sum: for an aligned chunk of 8 input bytes, gather
// the 8 corresponding `length` fields from grpc_chttp2_huffsyms and return
// their sum. Caller is responsible for the gating + boundary handling.
GRPC_SIMD_TARGET_AVX2
inline size_t huffman_length_sum_avx2(const uint8_t* in, size_t bytes) {
  size_t sum = 0;
  const __m256i ones = _mm256_set1_epi32(0xff);
  // The huffsym struct is {unsigned bits; unsigned length;} == 8 bytes.
  // Use base address = &huffsyms[0].length, scale = 8: gather reads
  //   *(int*)(base + index*8) = huffsyms[index].length.
  const int* length_base = reinterpret_cast<const int*>(
      reinterpret_cast<const char*>(&grpc_chttp2_huffsyms[0]) +
      offsetof(grpc_chttp2_huffsym, length));
  size_t i = 0;
  for (; i + 8 <= bytes; i += 8) {
    __m128i in8 = _mm_loadl_epi64(reinterpret_cast<const __m128i*>(in + i));
    __m256i indices = _mm256_cvtepu8_epi32(in8);
    __m256i lengths = _mm256_i32gather_epi32(length_base, indices, 8);
    // Mask to be defensive about width (length is small; mask is a no-op when
    // the field already fits in 32 bits, but keeps semantics clear).
    lengths = _mm256_and_si256(lengths, ones);
    // Horizontal sum of 8 32-bit lanes.
    __m128i lo = _mm256_castsi256_si128(lengths);
    __m128i hi = _mm256_extracti128_si256(lengths, 1);
    __m128i s = _mm_add_epi32(lo, hi);
    s = _mm_hadd_epi32(s, s);
    s = _mm_hadd_epi32(s, s);
    sum += static_cast<size_t>(_mm_cvtsi128_si32(s));
  }
  for (; i < bytes; ++i) {
    sum += grpc_chttp2_huffsyms[in[i]].length;
  }
  return sum;
}

}  // namespace
#endif  // GRPC_SIMD_HUFFMAN_X86

grpc_slice grpc_chttp2_huffman_compress(const grpc_slice& input) {
  size_t nbits;
  const uint8_t* in;
  uint8_t* out;
  grpc_slice output;
  uint64_t temp = 0;
  uint32_t temp_length = 0;

#ifdef GRPC_SIMD_HUFFMAN_X86
  // SIMD first pass: vectorized gather of huffsym lengths.
  if (grpc_core::simd::UseAvx2()) {
    nbits = huffman_length_sum_avx2(GRPC_SLICE_START_PTR(input),
                                    GRPC_SLICE_LENGTH(input));
  } else {
#endif
    nbits = 0;
    for (in = GRPC_SLICE_START_PTR(input); in != GRPC_SLICE_END_PTR(input);
         ++in) {
      nbits += grpc_chttp2_huffsyms[*in].length;
    }
#ifdef GRPC_SIMD_HUFFMAN_X86
  }
#endif

  output = GRPC_SLICE_MALLOC(nbits / 8 + (nbits % 8 != 0));
  out = GRPC_SLICE_START_PTR(output);
  for (in = GRPC_SLICE_START_PTR(input); in != GRPC_SLICE_END_PTR(input);
       ++in) {
    int sym = *in;
    temp <<= grpc_chttp2_huffsyms[sym].length;
    temp |= grpc_chttp2_huffsyms[sym].bits;
    temp_length += grpc_chttp2_huffsyms[sym].length;

    while (temp_length > 8) {
      temp_length -= 8;
      *out++ = static_cast<uint8_t>(temp >> temp_length);
    }
  }

  if (temp_length) {
    // NB: the following integer arithmetic operation needs to be in its
    // expanded form due to the "integral promotion" performed (see section
    // 3.2.1.1 of the C89 draft standard). A cast to the smaller container type
    // is then required to avoid the compiler warning
    *out++ =
        static_cast<uint8_t>(static_cast<uint8_t>(temp << (8u - temp_length)) |
                             static_cast<uint8_t>(0xffu >> temp_length));
  }

  GRPC_CHECK(out == GRPC_SLICE_END_PTR(output));

  return output;
}

struct huff_out {
  uint32_t temp;
  uint32_t temp_length;
  uint8_t* out;
};
static void enc_flush_some(huff_out* out) {
  while (out->temp_length > 8) {
    out->temp_length -= 8;
    *out->out++ = static_cast<uint8_t>(out->temp >> out->temp_length);
  }
}

static void enc_add2(huff_out* out, uint8_t a, uint8_t b, uint32_t* wire_size) {
  *wire_size += 2;
  b64_huff_sym sa = huff_alphabet[a];
  b64_huff_sym sb = huff_alphabet[b];
  out->temp = (out->temp << (sa.length + sb.length)) |
              (static_cast<uint32_t>(sa.bits) << sb.length) | sb.bits;
  out->temp_length +=
      static_cast<uint32_t>(sa.length) + static_cast<uint32_t>(sb.length);
  enc_flush_some(out);
}

static void enc_add1(huff_out* out, uint8_t a, uint32_t* wire_size) {
  *wire_size += 1;
  b64_huff_sym sa = huff_alphabet[a];
  out->temp = (out->temp << sa.length) | sa.bits;
  out->temp_length += sa.length;
  enc_flush_some(out);
}

grpc_slice grpc_chttp2_base64_encode_and_huffman_compress(
    const grpc_slice& input, uint32_t* wire_size) {
  size_t input_length = GRPC_SLICE_LENGTH(input);
  size_t input_triplets = input_length / 3;
  size_t tail_case = input_length % 3;
  size_t output_syms = (input_triplets * 4) + tail_xtra[tail_case];
  size_t max_output_bits = 11 * output_syms;
  size_t max_output_length = (max_output_bits / 8) + (max_output_bits % 8 != 0);
  grpc_slice output = GRPC_SLICE_MALLOC(max_output_length);
  const uint8_t* in = GRPC_SLICE_START_PTR(input);
  uint8_t* start_out = GRPC_SLICE_START_PTR(output);
  huff_out out;
  size_t i;

  out.temp = 0;
  out.temp_length = 0;
  out.out = start_out;
  *wire_size = 0;

  // encode full triplets
  for (i = 0; i < input_triplets; i++) {
    const uint8_t low_to_high = static_cast<uint8_t>((in[0] & 0x3) << 4);
    const uint8_t high_to_low = in[1] >> 4;
    enc_add2(&out, in[0] >> 2, low_to_high | high_to_low, wire_size);

    const uint8_t a = static_cast<uint8_t>((in[1] & 0xf) << 2);
    const uint8_t b = (in[2] >> 6);
    enc_add2(&out, a | b, in[2] & 0x3f, wire_size);
    in += 3;
  }

  // encode the remaining bytes
  switch (tail_case) {
    case 0:
      break;
    case 1:
      enc_add2(&out, in[0] >> 2, static_cast<uint8_t>((in[0] & 0x3) << 4),
               wire_size);
      in += 1;
      break;
    case 2: {
      const uint8_t low_to_high = static_cast<uint8_t>((in[0] & 0x3) << 4);
      const uint8_t high_to_low = in[1] >> 4;
      enc_add2(&out, in[0] >> 2, low_to_high | high_to_low, wire_size);
      enc_add1(&out, static_cast<uint8_t>((in[1] & 0xf) << 2), wire_size);
      in += 2;
      break;
    }
  }

  if (out.temp_length) {
    // NB: the following integer arithmetic operation needs to be in its
    // expanded form due to the "integral promotion" performed (see section
    // 3.2.1.1 of the C89 draft standard). A cast to the smaller container type
    // is then required to avoid the compiler warning
    *out.out++ = static_cast<uint8_t>(
        static_cast<uint8_t>(out.temp << (8u - out.temp_length)) |
        static_cast<uint8_t>(0xffu >> out.temp_length));
  }

  GRPC_CHECK(out.out <= GRPC_SLICE_END_PTR(output));
  GRPC_SLICE_SET_LENGTH(output, out.out - start_out);

  GRPC_CHECK(in == GRPC_SLICE_END_PTR(input));
  return output;
}
