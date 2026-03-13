#include "absl/container/flat_hash_map.h"
#include <iostream>

int main() {
    absl::flat_hash_map<int, int> m;
    m[1] = 2;
    std::cout << m[1] << std::endl;
    return 0;
}
