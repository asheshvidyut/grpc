use pyo3::prelude::*;

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

#[pyclass]
pub struct BaseEvent {
    event_type: String,
}

#[pymethods]
impl BaseEvent {
    #[new]
    fn new(event_type: &str) -> PyResult<Self> {
        Ok(BaseEvent {
            event_type: event_type.to_string(),
        })
    }

    fn get_type(&self) -> PyResult<String> {
        Ok(self.event_type.clone())
    }
}

#[pyclass]
pub struct CompressionAlgorithm {
    algorithm: String,
}

#[pymethods]
impl CompressionAlgorithm {
    #[new]
    fn new(algorithm: &str) -> PyResult<Self> {
        Ok(CompressionAlgorithm {
            algorithm: algorithm.to_string(),
        })
    }

    fn get_algorithm(&self) -> PyResult<String> {
        Ok(self.algorithm.clone())
    }
}

/// A Python module implemented in Rust.
#[pymodule]
fn grpc_rust_bindings(_py: Python, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register classes
    m.add_class::<Channel>()?;
    m.add_class::<Server>()?;
    m.add_class::<Call>()?;
    m.add_class::<CompletionQueue>()?;
    m.add_class::<CallCredentials>()?;
    m.add_class::<Metadata>()?;
    m.add_class::<Status>()?;
    m.add_class::<BaseEvent>()?;
    m.add_class::<CompressionAlgorithm>()?;

    // Async classes
    m.add_class::<AioChannel>()?;
    m.add_class::<AioServer>()?;
    m.add_class::<AioCall>()?;

    // Constants
    m.add("GRPC_STATUS_OK", 0)?;
    m.add("GRPC_STATUS_CANCELLED", 1)?;
    m.add("GRPC_STATUS_UNKNOWN", 2)?;
    m.add("GRPC_STATUS_INVALID_ARGUMENT", 3)?;
    m.add("GRPC_STATUS_DEADLINE_EXCEEDED", 4)?;
    m.add("GRPC_STATUS_NOT_FOUND", 5)?;
    m.add("GRPC_STATUS_ALREADY_EXISTS", 6)?;
    m.add("GRPC_STATUS_PERMISSION_DENIED", 7)?;
    m.add("GRPC_STATUS_UNAUTHENTICATED", 16)?;
    m.add("GRPC_STATUS_RESOURCE_EXHAUSTED", 8)?;
    m.add("GRPC_STATUS_FAILED_PRECONDITION", 9)?;
    m.add("GRPC_STATUS_ABORTED", 10)?;
    m.add("GRPC_STATUS_OUT_OF_RANGE", 11)?;
    m.add("GRPC_STATUS_UNIMPLEMENTED", 12)?;
    m.add("GRPC_STATUS_INTERNAL", 13)?;
    m.add("GRPC_STATUS_UNAVAILABLE", 14)?;
    m.add("GRPC_STATUS_DATA_LOSS", 15)?;

    // Compression constants
    m.add("GRPC_COMPRESSION_REQUEST_ALGORITHM_MD_KEY", "grpc-encoding")?;
    m.add("GRPC_COMPRESSION_CHANNEL_DEFAULT_ALGORITHM", "grpc.default_compression_algorithm")?;

    // Compression algorithm instances
    let none_algorithm = CompressionAlgorithm::new("none")?;
    let deflate_algorithm = CompressionAlgorithm::new("deflate")?;
    let gzip_algorithm = CompressionAlgorithm::new("gzip")?;

    m.add("CompressionAlgorithm", m.getattr("CompressionAlgorithm")?)?;
    m.add("none", none_algorithm)?;
    m.add("deflate", deflate_algorithm)?;
    m.add("gzip", gzip_algorithm)?;

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