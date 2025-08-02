use pyo3_build_config::add_extension_module_link_args;

fn main() {
    // Set compatibility flag for Python 3.13
    println!("cargo:rustc-env=PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1");
    pyo3_build_config::add_extension_module_link_args();
} 