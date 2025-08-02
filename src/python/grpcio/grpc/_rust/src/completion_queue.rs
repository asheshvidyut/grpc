use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyDict, PyList};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;
use grpcio::{CompletionQueue as GrpcCompletionQueue, CompletionQueueHandle};
use std::collections::VecDeque;

#[pyclass]
pub struct CompletionQueue {
    inner: Arc<Mutex<Option<GrpcCompletionQueue>>>,
    handle: Arc<Mutex<Option<CompletionQueueHandle>>>,
    events: Arc<Mutex<VecDeque<PyObject>>>,
    is_shutdown: bool,
}

#[pymethods]
impl CompletionQueue {
    #[new]
    fn new(_py: Python) -> PyResult<Self> {
        Ok(Self {
            inner: Arc::new(Mutex::new(None)),
            handle: Arc::new(Mutex::new(None)),
            events: Arc::new(Mutex::new(VecDeque::new())),
            is_shutdown: false,
        })
    }

    fn start(&self, _py: Python) -> PyResult<()> {
        if self.is_shutdown {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("CompletionQueue is shutdown"));
        }
        
        let inner = self.inner.clone();
        let handle = self.handle.clone();
        
        tokio::spawn(async move {
            let cq = GrpcCompletionQueue::new();
            let cq_handle = cq.handle();
            
            let mut inner_guard = inner.lock().await;
            *inner_guard = Some(cq);
            
            let mut handle_guard = handle.lock().await;
            *handle_guard = Some(cq_handle);
        });
        
        Ok(())
    }

    fn shutdown(&self, _py: Python) -> PyResult<()> {
        if self.is_shutdown {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("CompletionQueue already shutdown"));
        }
        
        self.is_shutdown = true;
        
        let inner = self.inner.clone();
        
        tokio::spawn(async move {
            let mut inner_guard = inner.lock().await;
            if let Some(cq) = inner_guard.take() {
                drop(cq); // This will shutdown the completion queue
            }
        });
        
        Ok(())
    }

    fn is_shutdown(&self) -> PyResult<bool> {
        Ok(self.is_shutdown)
    }

    fn next_event(&self, timeout: Option<f64>, _py: Python) -> PyResult<Option<PyObject>> {
        if self.is_shutdown {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("CompletionQueue is shutdown"));
        }
        
        let events = self.events.clone();
        
        tokio::spawn(async move {
            let mut events_guard = events.lock().await;
            events_guard.pop_front()
        });
        
        // For now, return None
        Ok(None)
    }

    fn add_event(&self, event: PyObject, _py: Python) -> PyResult<()> {
        if self.is_shutdown {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>("CompletionQueue is shutdown"));
        }
        
        let events = self.events.clone();
        
        tokio::spawn(async move {
            let mut events_guard = events.lock().await;
            events_guard.push_back(event);
        });
        
        Ok(())
    }

    fn get_event_count(&self, _py: Python) -> PyResult<usize> {
        let events = self.events.clone();
        
        tokio::spawn(async move {
            let events_guard = events.lock().await;
            events_guard.len()
        });
        
        Ok(0) // Simplified for now
    }
}

impl CompletionQueue {
    pub async fn get_inner_cq(&self) -> Option<GrpcCompletionQueue> {
        let guard = self.inner.lock().await;
        guard.clone()
    }

    pub async fn get_handle(&self) -> Option<CompletionQueueHandle> {
        let guard = self.handle.lock().await;
        guard.clone()
    }
} 