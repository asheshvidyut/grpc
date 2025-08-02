use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::{Channel as GrpcChannel, ChannelBuilder, Environment};
use std::collections::HashMap;

#[pyclass]
pub struct Channel {
    inner: Arc<Mutex<Option<GrpcChannel>>>,
    target: String,
    options: HashMap<String, String>,
}

#[pymethods]
impl Channel {
    #[new]
    fn new(target: String, options: Option<PyObject>, _py: Python) -> PyResult<Self> {
        let mut opts = HashMap::new();
        if let Some(opts_obj) = options {
            if let Ok(opts_dict) = opts_obj.downcast::<PyDict>(_py) {
                for (key, value) in opts_dict.iter() {
                    if let (Ok(k), Ok(v)) = (key.extract::<String>(), value.extract::<String>()) {
                        opts.insert(k, v);
                    }
                }
            }
        }
        
        Ok(Self {
            inner: Arc::new(Mutex::new(None)),
            target,
            options: opts,
        })
    }

    fn connect(&self, _py: Python) -> PyResult<()> {
        let target = self.target.clone();
        let options = self.options.clone();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let env = Arc::new(Environment::new(1));
            let mut builder = ChannelBuilder::new(env);
            
            // Apply options
            for (key, value) in options {
                builder = builder.raw_config_string(key, value);
            }
            
            let channel = builder.connect(&target);
            let mut inner_guard = inner.lock().await;
            *inner_guard = Some(channel);
        });
        
        Ok(())
    }

    fn disconnect(&self, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            *inner_guard = None;
        });
        
        Ok(())
    }

    fn is_connected(&self, _py: Python) -> PyResult<bool> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            inner_guard.is_some()
        });
        
        Ok(true) // Simplified for now
    }

    fn get_target(&self) -> PyResult<String> {
        Ok(self.target.clone())
    }

    fn get_options(&self) -> PyResult<PyObject> {
        Python::with_gil(|py| {
            let dict = PyDict::new(py);
            for (key, value) in &self.options {
                dict.set_item(key, value)?;
            }
            Ok(dict.into())
        })
    }
}

impl Channel {
    pub async fn get_inner_channel(&self) -> Option<GrpcChannel> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 