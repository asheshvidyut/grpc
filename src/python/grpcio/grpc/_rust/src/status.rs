use pyo3::prelude::*;

#[pyclass]
pub struct Status {
    code: i32,
}

#[pymethods]
impl Status {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Status { code: 0 })
    }
} 