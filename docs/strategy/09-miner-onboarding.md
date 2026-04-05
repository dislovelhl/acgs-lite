# Constitutional Governance Subnet — Miner Onboarding Guide

## What This Subnet Does

This subnet pays TAO for **governance deliberation** — human-in-the-loop judgment on
cases where AI constitutional rules conflict, are ambiguous, or require contextual
interpretation. Cases are escalated from the ACGS-2 governance engine when automated
validation cannot reach a clear decision.

You are not mining with GPUs. You are earning TAO by providing high-quality governance
decisions that pass peer validation and constitutional mesh verification.

## What Miners Actually Do

1. **Receive** an escalated governance case (constitutional conflict, edge case, etc.)
2. **Deliberate** — analyze the case against the constitution and produce a judgment
3. **Submit** your judgment with reasoning to the validator network
4. **Earn** TAO based on judgment quality, peer validation, and tier multiplier

Judgments are validated by multiple independent peers (MACI separation of powers —
you cannot validate your own output). A Merkle proof chain records every validation.

## Incentive Structure

| Tier | Requirements | TAO Multiplier |
|------|-------------|----------------|
| Apprentice | Start here | 1.0x |
| Journeyman | 10+ validated judgments, reputation >= 1.2 | 1.5x |
| Master | 50+ validated, reputation >= 1.5, domain specialist | 2.5x |
| Elder | 200+ validated, precedent-setting contributions | 4.0x |

Emission weight is computed from five signals (configurable weights):
- **Manifold trust** (30%): projected trust from the governance manifold
- **Reputation** (25%): constitutional mesh peer validation score
- **Tier multiplier** (20%): your tier bonus from the table above
- **Precedent contributions** (15%): accepted judgments that became governance precedent
- **Authenticity** (10%): human deliberation quality signal

Safeguards: max 40% of emissions to any single miner, minimum floor for all active miners.

## Hardware Requirements

Minimal — this is not GPU mining:
- Any machine that can run Python 3.11+
- Network connectivity to Bittensor testnet
- ~500MB disk for constitution files and local artifact store
- No GPU required

## Setup

### 1. Install Dependencies

```bash
# Create environment
python -m venv venv && source venv/bin/activate

# Install bittensor
pip install bittensor>=7.0.0

# Install constitutional_swarm
pip install -e packages/constitutional_swarm
```

### 2. Create or Import Wallet

```bash
# New wallet
btcli wallet new_coldkey --wallet.name miner
btcli wallet new_hotkey --wallet.name miner --wallet.hotkey default

# Fund on testnet (get test TAO from faucet)
btcli wallet faucet --wallet.name miner --subtensor.network test
```

### 3. Register on Subnet

```bash
btcli subnet register --wallet.name miner --wallet.hotkey default \
    --subtensor.network test --netuid <NETUID>
```

### 4. Get the Constitution

The subnet operates under a shared constitutional rule set. Download the current
version from the subnet owner or use the default:

```bash
# The constitution YAML defines the governance rules miners deliberate under.
# Your constitution hash must match the network's active hash, or your
# judgments will be rejected.
```

### 5. Start Mining

```bash
python packages/constitutional_swarm/scripts/testnet_deploy.py miner \
    --wallet-name miner \
    --wallet-hotkey default \
    --constitution path/to/constitution.yaml \
    --netuid <NETUID> \
    --port 8091 \
    --domains "privacy,finance,safety" \
    --capabilities "governance-judgment"
```

The miner will:
- Register on the metagraph
- Start an axon server listening for governance cases
- Process incoming DeliberationSynapses through your deliberation handler
- Run DNA pre-check on every judgment before submission
- Track stats (judgments submitted, acceptance rate, DNA latency)

### 6. Monitor

```bash
# Check registration
btcli wallet overview --wallet.name miner --subtensor.network test

# Watch subnet activity
btcli subnet list --subtensor.network test
```

## Custom Deliberation Handlers

The default handler returns template responses. For higher-quality judgments
(and higher TAO earnings), replace it with your own deliberation logic:

```python
async def my_handler(task: str, context: str, meta: dict) -> tuple[str, str]:
    """Custom deliberation handler.

    Args:
        task: The governance case description
        context: Domain context (privacy, finance, safety, etc.)
        meta: Additional metadata (impact_score, escalation_type, etc.)

    Returns:
        (judgment, reasoning) — your governance decision and its justification
    """
    # Option 1: Human-in-the-loop
    judgment = await prompt_human_operator(task, context)

    # Option 2: AI-assisted with human review
    draft = await llm_analyze(task, context)
    judgment = await human_review(draft)

    # Option 3: Specialized domain model
    judgment = await domain_model.decide(task, meta)

    return (judgment, reasoning)
```

## Constitution Grace Window

When the subnet owner rotates the constitution, there is a grace window where
both the old and new constitution hashes are accepted. Your miner handles this
automatically — no action needed during rotations.

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ConstitutionMismatchError` | Your constitution is outdated | Download latest constitution from subnet owner |
| `DNAPreCheckFailedError` | Your judgment violated constitutional rules | Review the violation list and adjust your handler |
| `UnknownMinerError` | Not registered with the validator | Ensure you're registered on the subnet metagraph |
| Low acceptance rate | Judgments not passing peer validation | Improve reasoning quality; study accepted precedents |
| Zero emissions | Below minimum tier or inactive | Submit more validated judgments to advance tier |
