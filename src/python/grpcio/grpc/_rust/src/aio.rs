use pyo3::prelude::*;

#[pyclass]
pub struct AioChannel {
    target: String,
}

#[pymethods]
impl AioChannel {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(AioChannel { target: "".to_string() })
    }
}

#[pyclass]
pub struct AioServer {
    started: bool,
}

#[pymethods]
impl AioServer {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(AioServer { started: false })
    }
}

#[pyclass]
pub struct AioCall {
    method: String,
}

#[pymethods]
impl AioCall {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(AioCall { method: "".to_string() })
    }
} 