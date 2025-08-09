use pyo3::prelude::*;

#[pyclass]
pub struct Channel {
    target: String,
    closed: bool,
}

#[pymethods]
impl Channel {
    #[new]
    fn new(target: &str) -> PyResult<Self> {
        Ok(Channel { 
            target: target.to_string(),
            closed: false,
        })
    }
    
    fn close(&self, _py: Python) -> PyResult<()> {
        Ok(())
    }
    
    fn get_target(&self) -> PyResult<String> {
        Ok(self.target.clone())
    }
} 