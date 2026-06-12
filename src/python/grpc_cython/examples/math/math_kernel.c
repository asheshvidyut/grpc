// math_kernel.c
void compute_matrix_c(float* a, float* b, float* out, int size) {
    for (int i = 0; i < size; i++) {
        out[i] = a[i] * b[i];
    }
}
