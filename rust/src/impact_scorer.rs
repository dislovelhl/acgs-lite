/// impact_scorer.rs — Candle-based DistilBERT impact scorer for ACGS-2.
///
/// Replaces the Python/PyTorch DistilBERT call at the score ≥ 0.8 deliberation gate.
/// Exposed to Python via PyO3 as `ImpactScorer`.
///
/// Model: distilbert-base-uncased fine-tuned for impact classification.
/// Output: f32 score in [0.0, 1.0] — sigmoid of positive-class logit.
///
/// Usage (Python):
///   from acgs_lite_rust import ImpactScorer
///   scorer = ImpactScorer(model_dir="/path/to/model", device="cpu")
///   score = scorer.score("deploy service without approval")
///   scores = scorer.score_batch(["action a", "action b"])
///
/// Constitutional Hash: 608508a9bd224290
use candle_core::{DType, Device, Tensor};
use candle_nn::VarBuilder;
use candle_transformers::models::distilbert::{Config, DistilBertModel};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::path::PathBuf;
use tokenizers::Tokenizer;

const MAX_SEQ_LEN: usize = 128;
const GATE_THRESHOLD: f32 = 0.8;

fn device_from_str(name: &str) -> candle_core::Result<Device> {
    match name {
        "cuda" | "gpu" => Device::new_cuda(0),
        "metal" => Device::new_metal(0),
        _ => Ok(Device::Cpu),
    }
}

/// Tokenize a single text into (input_ids, attention_mask) tensors.
fn tokenize(
    tokenizer: &Tokenizer,
    text: &str,
    device: &Device,
) -> candle_core::Result<(Tensor, Tensor)> {
    let encoding = tokenizer
        .encode(text, true)
        .map_err(|e| candle_core::Error::Msg(format!("tokenizer: {e}")))?;

    let ids: Vec<u32> = encoding.get_ids().iter().copied().take(MAX_SEQ_LEN).collect();
    let mask: Vec<u32> = encoding
        .get_attention_mask()
        .iter()
        .copied()
        .take(MAX_SEQ_LEN)
        .collect();

    let ids = Tensor::from_vec(ids, (1, ids.len()), device)?.to_dtype(DType::U32)?;
    let mask = Tensor::from_vec(mask, (1, mask.len()), device)?.to_dtype(DType::U32)?;
    Ok((ids, mask))
}

/// Tokenize a batch, padding to the longest sequence.
fn tokenize_batch(
    tokenizer: &Tokenizer,
    texts: &[&str],
    device: &Device,
) -> candle_core::Result<(Tensor, Tensor)> {
    let encodings: Vec<_> = texts
        .iter()
        .map(|t| {
            tokenizer
                .encode(*t, true)
                .map_err(|e| candle_core::Error::Msg(format!("tokenizer: {e}")))
        })
        .collect::<candle_core::Result<_>>()?;

    let max_len = encodings
        .iter()
        .map(|e| e.get_ids().len().min(MAX_SEQ_LEN))
        .max()
        .unwrap_or(1);

    let mut ids_buf: Vec<u32> = Vec::with_capacity(texts.len() * max_len);
    let mut mask_buf: Vec<u32> = Vec::with_capacity(texts.len() * max_len);

    for enc in &encodings {
        let raw_ids = enc.get_ids();
        let raw_mask = enc.get_attention_mask();
        let len = raw_ids.len().min(MAX_SEQ_LEN);
        ids_buf.extend_from_slice(&raw_ids[..len]);
        mask_buf.extend_from_slice(&raw_mask[..len]);
        // Pad to max_len
        for _ in len..max_len {
            ids_buf.push(0);
            mask_buf.push(0);
        }
    }

    let ids = Tensor::from_vec(ids_buf, (texts.len(), max_len), device)?.to_dtype(DType::U32)?;
    let mask = Tensor::from_vec(mask_buf, (texts.len(), max_len), device)?.to_dtype(DType::U32)?;
    Ok((ids, mask))
}

/// Run model forward pass and return sigmoid scores for each item in batch.
fn forward_scores(
    model: &DistilBertModel,
    classifier: &candle_nn::Linear,
    ids: &Tensor,
    mask: &Tensor,
) -> candle_core::Result<Vec<f32>> {
    // DistilBERT: take [CLS] token (index 0) from last hidden state
    let hidden = model.forward(ids, mask)?;
    let cls = hidden.i((.., 0, ..))?; // (batch, hidden_size)
    let logits = classifier.forward(&cls)?; // (batch, 2)
    // Positive-class logit → sigmoid score
    let pos_logits = logits.i((.., 1))?; // (batch,)
    let scores = candle_nn::ops::sigmoid(&pos_logits)?;
    let scores_vec: Vec<f32> = scores.to_dtype(DType::F32)?.to_vec1()?;
    Ok(scores_vec)
}

/// PyO3-exposed DistilBERT impact scorer.
#[pyclass]
pub struct ImpactScorer {
    model: DistilBertModel,
    classifier: candle_nn::Linear,
    tokenizer: Tokenizer,
    device: Device,
}

#[pymethods]
impl ImpactScorer {
    /// Load model from a local directory containing:
    ///   - `config.json`       — DistilBERT config
    ///   - `model.safetensors` — weights (or `pytorch_model.bin`)
    ///   - `tokenizer.json`    — HF fast tokenizer
    ///
    /// `device`: "cpu" | "cuda" | "metal"
    #[new]
    #[pyo3(signature = (model_dir, device = "cpu"))]
    fn new(model_dir: &str, device: &str) -> PyResult<Self> {
        let dev = device_from_str(device)
            .map_err(|e| PyRuntimeError::new_err(format!("device: {e}")))?;

        let dir = PathBuf::from(model_dir);

        // Load tokenizer
        let tokenizer = Tokenizer::from_file(dir.join("tokenizer.json"))
            .map_err(|e| PyRuntimeError::new_err(format!("tokenizer: {e}")))?;

        // Load config
        let config_str = std::fs::read_to_string(dir.join("config.json"))
            .map_err(|e| PyRuntimeError::new_err(format!("config: {e}")))?;
        let config: Config = serde_json::from_str(&config_str)
            .map_err(|e| PyRuntimeError::new_err(format!("config parse: {e}")))?;

        // Load weights — prefer safetensors
        let weights_path = if dir.join("model.safetensors").exists() {
            dir.join("model.safetensors")
        } else {
            dir.join("pytorch_model.bin")
        };

        let vb = unsafe {
            VarBuilder::from_mmaped_safetensors(&[weights_path], DType::F32, &dev)
                .map_err(|e| PyRuntimeError::new_err(format!("weights: {e}")))?
        };

        let model = DistilBertModel::load(vb.pp("distilbert"), &config)
            .map_err(|e| PyRuntimeError::new_err(format!("model: {e}")))?;

        // Classification head: hidden_size → 2 (binary: low/high impact)
        let classifier = candle_nn::linear(config.dim, 2, vb.pp("classifier"))
            .map_err(|e| PyRuntimeError::new_err(format!("classifier head: {e}")))?;

        Ok(Self { model, classifier, tokenizer, device: dev })
    }

    /// Score a single action string. Returns f32 in [0.0, 1.0].
    fn score(&self, text: &str) -> PyResult<f32> {
        let (ids, mask) = tokenize(&self.tokenizer, text, &self.device)
            .map_err(|e| PyRuntimeError::new_err(format!("tokenize: {e}")))?;
        let scores = forward_scores(&self.model, &self.classifier, &ids, &mask)
            .map_err(|e| PyRuntimeError::new_err(format!("forward: {e}")))?;
        Ok(scores.into_iter().next().unwrap_or(0.0))
    }

    /// Score a batch of texts. Returns list of f32 scores.
    fn score_batch(&self, texts: Vec<String>) -> PyResult<Vec<f32>> {
        let refs: Vec<&str> = texts.iter().map(String::as_str).collect();
        let (ids, mask) = tokenize_batch(&self.tokenizer, &refs, &self.device)
            .map_err(|e| PyRuntimeError::new_err(format!("tokenize_batch: {e}")))?;
        forward_scores(&self.model, &self.classifier, &ids, &mask)
            .map_err(|e| PyRuntimeError::new_err(format!("forward: {e}")))
    }

    /// Convenience: returns True if score ≥ 0.8 (deliberation gate).
    fn needs_deliberation(&self, text: &str) -> PyResult<bool> {
        Ok(self.score(text)? >= GATE_THRESHOLD)
    }
}
