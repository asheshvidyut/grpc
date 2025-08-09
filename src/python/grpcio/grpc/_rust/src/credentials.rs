use pyo3::prelude::*;

#[pyclass]
pub struct CallCredentials {
    name: String,
}

#[pymethods]
impl CallCredentials {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(CallCredentials { name: "".to_string() })
    }
} 