use ndarray::prelude::*;
use numpy::{PyArray2, PyReadonlyArray2};
use pyo3::prelude::*;

pub fn register_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sinkhorn_knopp_stabilize, m)?)?;
    Ok(())
}

/// Sinkhorn-Knopp algorithm for matrix stabilization.
/// weights: (n, m) input matrix
/// regularization: entropy regularization factor
/// iterations: number of Sinkhorn iterations
#[pyfunction]
pub fn sinkhorn_knopp_stabilize<'py>(
    py: Python<'py>,
    weights: PyReadonlyArray2<f32>,
    _regularization: f32,
    iterations: usize,
) -> PyResult<Bound<'py, PyArray2<f32>>> {
    let weights = weights.as_array();
    let (n, m) = weights.dim();

    // K = exp(-M / reg)
    let mut p = weights.to_owned();

    // Initialize scaling vectors

    let mut u = Array1::<f32>::ones(n);
    let mut v = Array1::<f32>::ones(m);

    for _ in 0..iterations {
        // u = 1 / (P * v)
        let pv = p.dot(&v);
        for i in 0..n {
            u[i] = 1.0 / (pv[i] + 1e-9);
        }

        // v = 1 / (P.T * u)
        let ptu = p.t().dot(&u);
        for j in 0..m {
            v[j] = 1.0 / (ptu[j] + 1e-9);
        }
    }

    // Result P' = diag(u) * P * diag(v)
    for i in 0..n {
        for j in 0..m {
            p[[i, j]] *= u[i] * v[j];
        }
    }

    Ok(PyArray2::from_array(py, &p))
}
