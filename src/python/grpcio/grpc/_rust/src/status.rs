use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::RpcStatus;

#[pyclass]
pub struct Status {
    inner: Arc<Mutex<Option<RpcStatus>>>,
    code: i32,
    message: String,
    details: String,
}

#[pymethods]
impl Status {
    #[new]
    fn new(code: i32, message: String, details: Option<String>) -> Self {
        Self {
            inner: Arc::new(Mutex::new(None)),
            code,
            message,
            details: details.unwrap_or_default(),
        }
    }

    fn get_code(&self) -> PyResult<i32> {
        Ok(self.code)
    }

    fn get_message(&self) -> PyResult<String> {
        Ok(self.message.clone())
    }

    fn get_details(&self) -> PyResult<String> {
        Ok(self.details.clone())
    }

    fn is_ok(&self) -> PyResult<bool> {
        Ok(self.code == 0) // GRPC_STATUS_OK
    }

    fn is_cancelled(&self) -> PyResult<bool> {
        Ok(self.code == 1) // GRPC_STATUS_CANCELLED
    }

    fn is_unknown(&self) -> PyResult<bool> {
        Ok(self.code == 2) // GRPC_STATUS_UNKNOWN
    }

    fn is_invalid_argument(&self) -> PyResult<bool> {
        Ok(self.code == 3) // GRPC_STATUS_INVALID_ARGUMENT
    }

    fn is_deadline_exceeded(&self) -> PyResult<bool> {
        Ok(self.code == 4) // GRPC_STATUS_DEADLINE_EXCEEDED
    }

    fn is_not_found(&self) -> PyResult<bool> {
        Ok(self.code == 5) // GRPC_STATUS_NOT_FOUND
    }

    fn is_already_exists(&self) -> PyResult<bool> {
        Ok(self.code == 6) // GRPC_STATUS_ALREADY_EXISTS
    }

    fn is_permission_denied(&self) -> PyResult<bool> {
        Ok(self.code == 7) // GRPC_STATUS_PERMISSION_DENIED
    }

    fn is_unauthenticated(&self) -> PyResult<bool> {
        Ok(self.code == 16) // GRPC_STATUS_UNAUTHENTICATED
    }

    fn is_resource_exhausted(&self) -> PyResult<bool> {
        Ok(self.code == 8) // GRPC_STATUS_RESOURCE_EXHAUSTED
    }

    fn is_failed_precondition(&self) -> PyResult<bool> {
        Ok(self.code == 9) // GRPC_STATUS_FAILED_PRECONDITION
    }

    fn is_aborted(&self) -> PyResult<bool> {
        Ok(self.code == 10) // GRPC_STATUS_ABORTED
    }

    fn is_out_of_range(&self) -> PyResult<bool> {
        Ok(self.code == 11) // GRPC_STATUS_OUT_OF_RANGE
    }

    fn is_unimplemented(&self) -> PyResult<bool> {
        Ok(self.code == 12) // GRPC_STATUS_UNIMPLEMENTED
    }

    fn is_internal(&self) -> PyResult<bool> {
        Ok(self.code == 13) // GRPC_STATUS_INTERNAL
    }

    fn is_unavailable(&self) -> PyResult<bool> {
        Ok(self.code == 14) // GRPC_STATUS_UNAVAILABLE
    }

    fn is_data_loss(&self) -> PyResult<bool> {
        Ok(self.code == 15) // GRPC_STATUS_DATA_LOSS
    }

    fn set_code(&self, code: i32, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(status) = inner_guard.as_mut() {
                // status.set_code(code);
            }
        });
        
        Ok(())
    }

    fn set_message(&self, message: String, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(status) = inner_guard.as_mut() {
                // status.set_message(message);
            }
        });
        
        Ok(())
    }

    fn set_details(&self, details: String, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(status) = inner_guard.as_mut() {
                // status.set_details(details);
            }
        });
        
        Ok(())
    }

    fn to_string(&self) -> PyResult<String> {
        Ok(format!("Status(code={}, message='{}', details='{}')", 
                   self.code, self.message, self.details))
    }
}

impl Status {
    pub async fn get_inner_status(&self) -> Option<RpcStatus> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 