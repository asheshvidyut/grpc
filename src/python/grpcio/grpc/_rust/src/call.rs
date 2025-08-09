use pyo3::prelude::*;

#[pyclass]
pub struct Call {
    method: String,
}

#[pymethods]
impl Call {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Call { method: "".to_string() })
    }
    
    fn start_batch(&self, _py: Python) -> PyResult<()> {
        Ok(())
    }
} 