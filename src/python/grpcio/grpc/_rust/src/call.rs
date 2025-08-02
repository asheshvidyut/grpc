use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::{Call as GrpcCall, CallOption, WriteFlags, RpcStatus};
use std::collections::HashMap;

#[pyclass]
pub struct Call {
    inner: Arc<Mutex<Option<GrpcCall>>>,
    method: String,
    deadline: Option<f64>,
    metadata: HashMap<String, String>,
    is_cancelled: bool,
    is_done: bool,
}

#[pymethods]
impl Call {
    #[new]
    fn new(method: String, deadline: Option<f64>, metadata: Option<PyObject>, _py: Python) -> PyResult<Self> {
        let mut meta = HashMap::new();
        if let Some(meta_obj) = metadata {
            if let Ok(meta_dict) = meta_obj.downcast::<PyDict>(_py) {
                for (key, value) in meta_dict.iter() {
                    if let (Ok(k), Ok(v)) = (key.extract::<String>(), value.extract::<String>()) {
                        meta.insert(k, v);
                    }
                }
            }
        }
        
        Ok(Self {
            inner: Arc::new(Mutex::new(None)),
            method,
            deadline,
            metadata: meta,
            is_cancelled: false,
            is_done: false,
        })
    }

    fn start_call(&self, channel: PyObject, _py: Python) -> PyResult<()> {
        let method = self.method.clone();
        let deadline = self.deadline;
        let metadata = self.metadata.clone();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            // This would need to be implemented with actual gRPC call creation
            // For now, we'll create a placeholder
            let mut inner_guard = inner.lock().await;
            // *inner_guard = Some(call);
        });
        
        Ok(())
    }

    fn cancel(&self, _py: Python) -> PyResult<()> {
        if self.is_done {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Call already done"));
        }
        
        self.is_cancelled = true;
        
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(call) = inner_guard.as_mut() {
                // call.cancel();
            }
        });
        
        Ok(())
    }

    fn is_cancelled(&self) -> PyResult<bool> {
        Ok(self.is_cancelled)
    }

    fn is_done(&self) -> PyResult<bool> {
        Ok(self.is_done)
    }

    fn get_method(&self) -> PyResult<String> {
        Ok(self.method.clone())
    }

    fn get_deadline(&self) -> PyResult<Option<f64>> {
        Ok(self.deadline)
    }

    fn get_metadata(&self) -> PyResult<PyObject> {
        Python::with_gil(|py| {
            let dict = PyDict::new(py);
            for (key, value) in &self.metadata {
                dict.set_item(key, value)?;
            }
            Ok(dict.into())
        })
    }

    fn send_message(&self, message: PyBytes, _py: Python) -> PyResult<()> {
        if self.is_done {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Call already done"));
        }
        
        if self.is_cancelled {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Call is cancelled"));
        }
        
        let data = message.as_bytes().to_vec();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            if let Some(call) = inner_guard.as_ref() {
                // call.write_all(&data).await;
            }
        });
        
        Ok(())
    }

    fn recv_message(&self, _py: Python) -> PyResult<PyObject> {
        if self.is_done {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Call already done"));
        }
        
        if self.is_cancelled {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Call is cancelled"));
        }
        
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            if let Some(call) = inner_guard.as_ref() {
                // let data = call.read_all().await;
                // return data;
            }
        });
        
        // For now, return empty bytes
        Python::with_gil(|py| {
            let bytes = PyBytes::new(py, &[]);
            Ok(bytes.into())
        })
    }

    fn finish(&self, _py: Python) -> PyResult<()> {
        self.is_done = true;
        
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(call) = inner_guard.as_mut() {
                // call.finish().await;
            }
        });
        
        Ok(())
    }
}

impl Call {
    pub async fn get_inner_call(&self) -> Option<GrpcCall> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 