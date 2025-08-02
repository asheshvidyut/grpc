use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use std::collections::HashMap;

#[pyclass]
pub struct Metadata {
    inner: Arc<Mutex<HashMap<String, String>>>,
}

#[pymethods]
impl Metadata {
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
            inner: Arc::new(Mutex::new(meta)),
        })
    }

    fn add(&self, key: String, value: String, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            inner_guard.insert(key, value);
        });
        
        Ok(())
    }

    fn get(&self, key: String, _py: Python) -> PyResult<Option<String>> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            inner_guard.get(&key).cloned()
        });
        
        Ok(None) // Simplified for now
    }

    fn remove(&self, key: String, _py: Python) -> PyResult<Option<String>> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            inner_guard.remove(&key)
        });
        
        Ok(None) // Simplified for now
    }

    fn clear(&self, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            inner_guard.clear();
        });
        
        Ok(())
    }

    fn keys(&self, _py: Python) -> PyResult<PyObject> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            let keys: Vec<String> = inner_guard.keys().cloned().collect();
            keys
        });
        
        // For now, return empty list
        Python::with_gil(|py| {
            let list = PyList::new(py, &[]);
            Ok(list.into())
        })
    }

    fn values(&self, _py: Python) -> PyResult<PyObject> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            let values: Vec<String> = inner_guard.values().cloned().collect();
            values
        });
        
        // For now, return empty list
        Python::with_gil(|py| {
            let list = PyList::new(py, &[]);
            Ok(list.into())
        })
    }

    fn items(&self, _py: Python) -> PyResult<PyObject> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            let items: Vec<(String, String)> = inner_guard.iter().map(|(k, v)| (k.clone(), v.clone())).collect();
            items
        });
        
        // For now, return empty list
        Python::with_gil(|py| {
            let list = PyList::new(py, &[]);
            Ok(list.into())
        })
    }

    fn len(&self, _py: Python) -> PyResult<usize> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            inner_guard.len()
        });
        
        Ok(0) // Simplified for now
    }

    fn is_empty(&self, _py: Python) -> PyResult<bool> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            inner_guard.is_empty()
        });
        
        Ok(true) // Simplified for now
    }

    fn to_dict(&self, _py: Python) -> PyResult<PyObject> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let inner_guard = inner.lock().await;
            inner_guard.clone()
        });
        
        // For now, return empty dict
        Python::with_gil(|py| {
            let dict = PyDict::new(py);
            Ok(dict.into())
        })
    }

    fn from_dict(&self, metadata: PyObject, _py: Python) -> PyResult<()> {
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            inner_guard.clear();
            
            // This would populate from the Python dict
            // For now, we'll leave it empty
        });
        
        Ok(())
    }
}

impl Metadata {
    pub async fn get_inner_metadata(&self) -> HashMap<String, String> {
        let guard = self.inner.lock().await;
        guard.clone()
    }
} 