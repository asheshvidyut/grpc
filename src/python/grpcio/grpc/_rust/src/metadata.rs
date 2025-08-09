use pyo3::prelude::*;

#[pyclass]
pub struct Metadata {
    data: String,
}

#[pymethods]
impl Metadata {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Metadata { data: "".to_string() })
    }
} 