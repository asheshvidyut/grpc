use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::{CallCredentials as GrpcCallCredentials, ChannelCredentials as GrpcChannelCredentials};
use std::collections::HashMap;

#[pyclass]
pub struct CallCredentials {
    inner: Arc<Mutex<Option<GrpcCallCredentials>>>,
    metadata: HashMap<String, String>,
}

#[pyclass]
pub struct ChannelCredentials {
    inner: Arc<Mutex<Option<GrpcChannelCredentials>>>,
    ssl_enabled: bool,
    cert_file: Option<String>,
    key_file: Option<String>,
    ca_file: Option<String>,
}

#[pymethods]
impl CallCredentials {
    #[new]
    fn new(metadata: Option<PyObject>, _py: Python) -> PyResult<Self> {
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
            metadata: meta,
        })
    }

    fn add_metadata(&self, key: String, value: String, _py: Python) -> PyResult<()> {
        self.metadata.insert(key, value);
        Ok(())
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

    fn create_call_credentials(&self, _py: Python) -> PyResult<()> {
        let metadata = self.metadata.clone();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            // This would create actual gRPC call credentials from metadata
            // For now, we'll create a placeholder
            let mut inner_guard = inner.lock().await;
            // *inner_guard = Some(credentials);
        });
        
        Ok(())
    }
}

#[pymethods]
impl ChannelCredentials {
    #[new]
    fn new(ssl_enabled: bool, cert_file: Option<String>, key_file: Option<String>, ca_file: Option<String>, _py: Python) -> PyResult<Self> {
        Ok(Self {
            inner: Arc::new(Mutex::new(None)),
            ssl_enabled,
            cert_file,
            key_file,
            ca_file,
        })
    }

    fn create_channel_credentials(&self, _py: Python) -> PyResult<()> {
        let ssl_enabled = self.ssl_enabled;
        let cert_file = self.cert_file.clone();
        let key_file = self.key_file.clone();
        let ca_file = self.ca_file.clone();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            if ssl_enabled {
                // This would create SSL channel credentials
                // For now, we'll create a placeholder
                let mut inner_guard = inner.lock().await;
                // *inner_guard = Some(credentials);
            } else {
                // Create insecure credentials
                let mut inner_guard = inner.lock().await;
                // *inner_guard = Some(GrpcChannelCredentials::insecure());
            }
        });
        
        Ok(())
    }

    fn is_ssl_enabled(&self) -> PyResult<bool> {
        Ok(self.ssl_enabled)
    }

    fn get_cert_file(&self) -> PyResult<Option<String>> {
        Ok(self.cert_file.clone())
    }

    fn get_key_file(&self) -> PyResult<Option<String>> {
        Ok(self.key_file.clone())
    }

    fn get_ca_file(&self) -> PyResult<Option<String>> {
        Ok(self.ca_file.clone())
    }
}

impl CallCredentials {
    pub async fn get_inner_credentials(&self) -> Option<GrpcCallCredentials> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
}

impl ChannelCredentials {
    pub async fn get_inner_credentials(&self) -> Option<GrpcChannelCredentials> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 