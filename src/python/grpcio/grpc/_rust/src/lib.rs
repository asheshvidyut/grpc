use pyo3::prelude::*;
use pyo3::wrap_pyfunction;
use pyo3::types::{PyBytes, PyDict, PyList, PyTuple};
use std::sync::Arc;
use tokio::sync::Mutex;
use anyhow::Result;

mod channel;
mod server;
mod call;
mod completion_queue;
mod credentials;
mod metadata;
mod status;
mod aio;

use channel::*;
use server::*;
use call::*;
use completion_queue::*;
use credentials::*;
use metadata::*;
use status::*;
use aio::*;

/// A Python module implemented in Rust.
#[pymodule]
fn grpc_rust_bindings(_py: Python, m: &PyModule) -> PyResult<()> {
    // Initialize logging
    env_logger::init();
    
    // Register classes
    m.add_class::<Channel>()?;
    m.add_class::<Server>()?;
    m.add_class::<Call>()?;
    m.add_class::<CompletionQueue>()?;
    m.add_class::<CallCredentials>()?;
    m.add_class::<Metadata>()?;
    m.add_class::<Status>()?;
    
    // Async classes
    m.add_class::<AioChannel>()?;
    m.add_class::<AioServer>()?;
    m.add_class::<AioCall>()?;
    
    // Constants
    m.add("GRPC_STATUS_OK", GRPC_STATUS_OK)?;
    m.add("GRPC_STATUS_CANCELLED", GRPC_STATUS_CANCELLED)?;
    m.add("GRPC_STATUS_UNKNOWN", GRPC_STATUS_UNKNOWN)?;
    m.add("GRPC_STATUS_INVALID_ARGUMENT", GRPC_STATUS_INVALID_ARGUMENT)?;
    m.add("GRPC_STATUS_DEADLINE_EXCEEDED", GRPC_STATUS_DEADLINE_EXCEEDED)?;
    m.add("GRPC_STATUS_NOT_FOUND", GRPC_STATUS_NOT_FOUND)?;
    m.add("GRPC_STATUS_ALREADY_EXISTS", GRPC_STATUS_ALREADY_EXISTS)?;
    m.add("GRPC_STATUS_PERMISSION_DENIED", GRPC_STATUS_PERMISSION_DENIED)?;
    m.add("GRPC_STATUS_UNAUTHENTICATED", GRPC_STATUS_UNAUTHENTICATED)?;
    m.add("GRPC_STATUS_RESOURCE_EXHAUSTED", GRPC_STATUS_RESOURCE_EXHAUSTED)?;
    m.add("GRPC_STATUS_FAILED_PRECONDITION", GRPC_STATUS_FAILED_PRECONDITION)?;
    m.add("GRPC_STATUS_ABORTED", GRPC_STATUS_ABORTED)?;
    m.add("GRPC_STATUS_OUT_OF_RANGE", GRPC_STATUS_OUT_OF_RANGE)?;
    m.add("GRPC_STATUS_UNIMPLEMENTED", GRPC_STATUS_UNIMPLEMENTED)?;
    m.add("GRPC_STATUS_INTERNAL", GRPC_STATUS_INTERNAL)?;
    m.add("GRPC_STATUS_UNAVAILABLE", GRPC_STATUS_UNAVAILABLE)?;
    m.add("GRPC_STATUS_DATA_LOSS", GRPC_STATUS_DATA_LOSS)?;
    
    Ok(())
}

// Re-export constants for use in other modules
pub const GRPC_STATUS_OK: i32 = 0;
pub const GRPC_STATUS_CANCELLED: i32 = 1;
pub const GRPC_STATUS_UNKNOWN: i32 = 2;
pub const GRPC_STATUS_INVALID_ARGUMENT: i32 = 3;
pub const GRPC_STATUS_DEADLINE_EXCEEDED: i32 = 4;
pub const GRPC_STATUS_NOT_FOUND: i32 = 5;
pub const GRPC_STATUS_ALREADY_EXISTS: i32 = 6;
pub const GRPC_STATUS_PERMISSION_DENIED: i32 = 7;
pub const GRPC_STATUS_UNAUTHENTICATED: i32 = 16;
pub const GRPC_STATUS_RESOURCE_EXHAUSTED: i32 = 8;
pub const GRPC_STATUS_FAILED_PRECONDITION: i32 = 9;
pub const GRPC_STATUS_ABORTED: i32 = 10;
pub const GRPC_STATUS_OUT_OF_RANGE: i32 = 11;
pub const GRPC_STATUS_UNIMPLEMENTED: i32 = 12;
pub const GRPC_STATUS_INTERNAL: i32 = 13;
pub const GRPC_STATUS_UNAVAILABLE: i32 = 14;
pub const GRPC_STATUS_DATA_LOSS: i32 = 15; 