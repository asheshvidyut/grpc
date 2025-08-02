use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::{Server as GrpcServer, ServerBuilder, Environment};
use std::collections::HashMap;
use std::net::SocketAddr;

#[pyclass]
pub struct Server {
    inner: Arc<Mutex<Option<GrpcServer>>>,
    address: String,
    port: u16,
    options: HashMap<String, String>,
    is_started: bool,
    is_shutdown: bool,
}

#[pyclass]
pub struct RegisteredMethod {
    method_name: String,
    server: PyObject,
}

#[pymethods]
impl RegisteredMethod {
    #[new]
    fn new(method_name: String, server: PyObject) -> Self {
        Self {
            method_name,
            server,
        }
    }

    fn get_method_name(&self) -> PyResult<String> {
        Ok(self.method_name.clone())
    }
}

#[pymethods]
impl Server {
    #[new]
    fn new(address: String, port: u16, options: Option<PyObject>, _py: Python) -> PyResult<Self> {
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
            address,
            port,
            options: opts,
            is_started: false,
            is_shutdown: false,
        })
    }

    fn start(&self, _py: Python) -> PyResult<()> {
        if self.is_started {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Server already started"));
        }
        
        if self.is_shutdown {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Server is shutdown"));
        }
        
        let address = self.address.clone();
        let port = self.port;
        let options = self.options.clone();
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let env = Arc::new(Environment::new(1));
            let mut builder = ServerBuilder::new(env);
            
            // Apply options
            for (key, value) in options {
                builder = builder.raw_config_string(key, value);
            }
            
            let addr: SocketAddr = format!("{}:{}", address, port).parse().unwrap();
            let server = builder.bind(format!("{}", addr)).build().unwrap();
            
            let mut inner_guard = inner.lock().await;
            *inner_guard = Some(server);
        });
        
        Ok(())
    }

    fn stop(&self, _py: Python) -> PyResult<()> {
        if !self.is_started {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Server not started"));
        }
        
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(server) = inner_guard.take() {
                drop(server); // This will shutdown the server
            }
        });
        
        Ok(())
    }

    fn shutdown(&self, _py: Python) -> PyResult<()> {
        self.is_shutdown = true;
        self.stop(_py)
    }

    fn is_started(&self) -> PyResult<bool> {
        Ok(self.is_started)
    }

    fn is_shutdown(&self) -> PyResult<bool> {
        Ok(self.is_shutdown)
    }

    fn get_address(&self) -> PyResult<String> {
        Ok(self.address.clone())
    }

    fn get_port(&self) -> PyResult<u16> {
        Ok(self.port)
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

    fn register_method(&self, method_name: String, _py: Python) -> PyResult<RegisteredMethod> {
        if !self.is_started {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("Server not started"));
        }
        
        Ok(RegisteredMethod::new(method_name, self.into()))
    }
}

impl Server {
    pub async fn get_inner_server(&self) -> Option<GrpcServer> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 