use pyo3::prelude::*;

#[pyclass]
pub struct Server {
    started: bool,
}

#[pymethods]
impl Server {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Server { started: false })
    }
    
    fn start(&self, _py: Python) -> PyResult<()> {
        Ok(())
    }
    
    fn stop(&self, _py: Python) -> PyResult<()> {
        Ok(())
    }
} 