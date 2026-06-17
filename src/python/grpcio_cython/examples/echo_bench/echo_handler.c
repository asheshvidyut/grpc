#include <string.h>

void echo_c(const char* in_str, char* out_str, int len) {
    memcpy(out_str, in_str, len);
    out_str[len] = '\0';
}
