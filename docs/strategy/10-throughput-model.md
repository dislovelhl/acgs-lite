# Throughput Model — On-Chain / Off-Chain Sizing

Addresses CEO review flag: "on-chain/off-chain split not sized against real workload."

## Bittensor Chain Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Block time | ~12 seconds | Substrate runtime |
| Blocks/day | ~7,200 | 86,400 / 12 |
| Tempo (epoch) | 360 blocks (~72 min) | Subnet hyperparameter, configurable |
| Epochs/day | ~20 | 7,200 / 360 |
| set_weights rate limit | 1 per tempo per validator | Chain enforced |
| commit_weights | 1 per tempo per validator (commit/reveal) | Newer mechanism |
| Extrinsic size limit | ~4 MB per block | Substrate default |
| Testnet cost | Free (faucet TAO) | Test network |

## Our Write Pattern

The subnet has two on-chain write paths:

### 1. Weight Setting (Validator → Chain)

**What:** Validator calls `set_weights` once per epoch with normalized emission weights
for all registered miners.

**Frequency:** Fixed at 1 call per epoch per validator = **~20 writes/day/validator**.

**Payload:** Array of (uid, weight) pairs. For 100 miners: ~1.6 KB per call.

**Bottleneck:** Not throughput — this is rate-limited by tempo, not by us.

### 2. Batch Merkle Anchor (ChainAnchor → Chain)

**What:** ChainAnchor accumulates MeshProof evidence into batches (default: 100 proofs),
computes a Merkle root, and submits a single on-chain anchor per batch.

**Payload per anchor:**
- Batch Merkle root: 64 bytes (SHA-256 hex)
- Constitutional hash: 16 bytes
- Proof count: 4 bytes
- Total: ~84 bytes per anchor extrinsic

**This is the scaling path.** 100 governance decisions produce 1 on-chain write.

## Sizing at Target Volumes

### Assumptions

- 1 validator sets weights per epoch (20/day)
- ChainAnchor batch_size = 100 (configurable)
- Each governance decision = 1 MeshProof = 1 proof in the batch
- Anchor writes are not rate-limited by tempo (custom extrinsic, not set_weights)

### Volume Projections

| Metric | 1K decisions/day | 10K decisions/day | 100K decisions/day |
|--------|:---:|:---:|:---:|
| **Decisions** | 1,000 | 10,000 | 100,000 |
| **Anchor writes** (batch=100) | 10 | 100 | 1,000 |
| **Weight writes** (1 validator) | 20 | 20 | 20 |
| **Total on-chain writes/day** | 30 | 120 | 1,020 |
| **Writes/block** | 0.004 | 0.017 | 0.14 |
| **On-chain data/day** | 2.5 KB | 10 KB | 86 KB |
| **Off-chain data/day** | ~5 MB | ~50 MB | ~500 MB |
| **Utilization of chain capacity** | <0.1% | <0.1% | ~0.5% |

### Off-Chain Storage (per decision)

| Component | Size | Storage |
|-----------|------|---------|
| JudgmentSynapse (judgment + reasoning) | ~2 KB | ArtifactStore |
| MeshProof (votes, Merkle chain) | ~1 KB | ArtifactStore |
| PrecedentRecord (if accepted) | ~1 KB | PrecedentStore |
| ArweaveAuditLog entry | ~500 bytes | Arweave (Phase 2.3) |
| Total per decision | ~5 KB | Off-chain |

## Bottleneck Analysis

| Volume | Bottleneck | Severity |
|--------|-----------|----------|
| 1K/day | None — well within all limits | Green |
| 10K/day | Miner throughput — need ~7 decisions/minute per miner with 10 miners | Yellow |
| 100K/day | Miner count — need 50+ active miners processing ~1.4 decisions/minute each | Red |

The chain is **not** the bottleneck at any realistic volume. At 100K decisions/day,
we use <1% of available block capacity.

**The real bottleneck is miner supply:**
- At 10K/day with 10 miners: each miner handles ~17 cases/hour
- At 100K/day with 50 miners: each miner handles ~83 cases/hour
- Human-in-the-loop tops out at ~10-20 cases/hour per deliberator
- AI-assisted deliberation extends this to ~100+/hour

## Batch Size Tuning

| Batch Size | Anchors at 10K/day | Verification Latency | On-Chain Writes |
|------------|:---:|:---:|:---:|
| 10 | 1,000 | ~seconds | 1,000/day |
| 100 (default) | 100 | ~minutes | 100/day |
| 1,000 | 10 | ~hours | 10/day |

Recommendation: **batch_size=100** is correct for testnet. Increase to 1,000
only after testnet validates that verification latency is acceptable.

## Decision: On-Chain vs Off-Chain Split

The current design is **correct**:

| On-Chain | Off-Chain |
|----------|-----------|
| Batch Merkle roots | Individual proof content |
| Constitutional hash per batch | Judgment reasoning text |
| Proof count per batch | Reputation scores |
| Emission weights per epoch | Authenticity signals |
| Block height timestamps | Full audit logs (Arweave) |

At 100K decisions/day, on-chain storage grows by ~86 KB/day (~31 MB/year).
Off-chain storage grows by ~500 MB/day (~183 GB/year) — appropriate for
ArtifactStore + Arweave.

## Testnet Validation Criteria (from roadmap)

The throughput model predicts no chain capacity issues. Testnet should validate:

1. **Anchor latency**: Time from batch flush to on-chain confirmation < 30s
2. **Weight setting reliability**: set_weights succeeds every epoch without conflicts
3. **Miner processing rate**: Sustained throughput per miner (target: 10+ cases/hour)
4. **Off-chain storage growth**: ArtifactStore disk usage at target volume
5. **Merkle verification**: verify_membership() latency at batch_size=100
