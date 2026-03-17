use ndarray::parallel::prelude::*;
use ndarray::{Array1, Array2, ArrayView2, ArrayView3, Axis};
use numpy::{PyArray2, PyReadonlyArray2, PyReadonlyArray3};
use pyo3::prelude::*;

pub fn register_module(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(mean_pooling_f32, m)?)?;
    Ok(())
}

/// Internal implementation of mean pooling for BERT embeddings.
pub fn mean_pooling_internal(
    embeddings: ArrayView3<f32>,
    attention_mask: ArrayView2<i64>,
) -> Array2<f32> {
    let (batch_size, seq_len, embed_dim) = embeddings.dim();
    let mut output = Array2::<f32>::zeros((batch_size, embed_dim));

    output
        .axis_iter_mut(Axis(0))
        .into_par_iter()
        .enumerate()
        .for_each(|(b, mut out_row)| {
            let mut sum = Array1::<f32>::zeros(embed_dim);
            let mut count = 0.0;

            for s in 0..seq_len {
                if attention_mask[[b, s]] == 1 {
                    for d in 0..embed_dim {
                        sum[d] += embeddings[[b, s, d]];
                    }
                    count += 1.0;
                }
            }

            if count > 0.0 {
                for d in 0..embed_dim {
                    out_row[d] = sum[d] / count;
                }
            }
        });

    output
}

/// Mean Pooling implementation for BERT embeddings.
#[pyfunction]
pub fn mean_pooling_f32<'py>(
    py: Python<'py>,
    embeddings: PyReadonlyArray3<f32>,
    attention_mask: PyReadonlyArray2<i64>,
) -> PyResult<Bound<'py, PyArray2<f32>>> {
    let embeddings = embeddings.as_array();
    let attention_mask = attention_mask.as_array();
    let output = mean_pooling_internal(embeddings, attention_mask);
    Ok(PyArray2::from_array(py, &output))
}
