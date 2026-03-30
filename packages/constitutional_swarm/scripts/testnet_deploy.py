#!/usr/bin/env python3
"""Bittensor Testnet Deployment Script for Constitutional Governance Subnet.

Usage:
    # Register subnet on testnet
    python scripts/testnet_deploy.py register --wallet-name <name> --wallet-hotkey <key>

    # Start miner
    python scripts/testnet_deploy.py miner --wallet-name <name> --wallet-hotkey <key> \
        --constitution constitution.yaml --netuid <id>

    # Start validator
    python scripts/testnet_deploy.py validator --wallet-name <name> --wallet-hotkey <key> \
        --constitution constitution.yaml --netuid <id>

Requirements:
    pip install bittensor>=7.0.0

Note: This script requires the bittensor package. The constitutional_swarm
primitives work without it, but deployment needs the real bt.subtensor and
bt.wallet interfaces.
"""

from __future__ import annotations

import argparse
import sys


def _check_bittensor() -> None:
    """Verify bittensor package is installed."""
    try:
        import bittensor  # noqa: F401
    except ImportError:
        print("ERROR: bittensor package not installed.")
        print("  pip install bittensor>=7.0.0")
        sys.exit(1)


def cmd_register(args: argparse.Namespace) -> None:
    """Register a new subnet on testnet."""
    _check_bittensor()
    import bittensor as bt

    wallet = bt.wallet(name=args.wallet_name, hotkey=args.wallet_hotkey)
    subtensor = bt.subtensor(network="test")

    print(f"Registering subnet on testnet with wallet {wallet.name}...")
    print(f"  Wallet coldkey: {wallet.coldkeypub.ss58_address}")
    print(f"  Network: test")

    # Register subnet
    success = subtensor.register_subnet(wallet=wallet)
    if success:
        print("Subnet registered successfully.")
        print(f"  Use --netuid flag with the assigned netuid for miner/validator commands.")
    else:
        print("ERROR: Subnet registration failed.")
        sys.exit(1)


def cmd_miner(args: argparse.Namespace) -> None:
    """Start a constitutional governance miner on testnet."""
    _check_bittensor()
    import asyncio

    import bittensor as bt

    from constitutional_swarm.bittensor.miner import ConstitutionalMiner
    from constitutional_swarm.bittensor.protocol import MinerConfig

    wallet = bt.wallet(name=args.wallet_name, hotkey=args.wallet_hotkey)
    subtensor = bt.subtensor(network="test")

    print(f"Starting Constitutional Miner on testnet (netuid={args.netuid})...")
    print(f"  Constitution: {args.constitution}")
    print(f"  Wallet: {wallet.name} / {wallet.hotkey_str}")

    # Create the constitutional miner
    async def _deliberation_handler(
        task: str, context: str, meta: dict
    ) -> tuple[str, str]:
        """Default AI-assisted deliberation handler.

        In production, replace with human-in-the-loop or
        specialized LLM pipeline.
        """
        return (
            f"Governance judgment for domain {context}: "
            "this case requires balancing competing constitutional principles. "
            "After analysis, the recommended approach prioritizes safety "
            "while maintaining transparency.",
            "Balanced analysis considering all stakeholder perspectives "
            "and constitutional requirements.",
        )

    config = MinerConfig(
        constitution_path=args.constitution,
        agent_id=wallet.hotkey_str,
        capabilities=tuple(args.capabilities.split(",")) if args.capabilities else ("governance-judgment",),
        domains=tuple(args.domains.split(",")) if args.domains else ("general",),
    )

    miner = ConstitutionalMiner(
        config=config,
        deliberation_handler=_deliberation_handler,
    )

    print(f"  Constitution hash: {miner.constitution_hash}")
    print(f"  Agent ID: {config.agent_id}")
    print(f"  Capabilities: {config.capabilities}")
    print(f"  Domains: {config.domains}")

    # Register on the metagraph
    subtensor.register(wallet=wallet, netuid=args.netuid)
    print(f"  Registered on metagraph (netuid={args.netuid})")

    # Set up axon to serve the miner's forward function
    axon = bt.axon(wallet=wallet, port=args.port)

    async def _forward(synapse: bt.Synapse) -> bt.Synapse:
        """Bridge bt.Synapse to ConstitutionalMiner.process()."""
        from constitutional_swarm.bittensor.synapses import DeliberationSynapse

        # Convert bt.Synapse fields to our DeliberationSynapse
        delib = DeliberationSynapse(
            task_id=getattr(synapse, "task_id", "unknown"),
            task_dag_json=getattr(synapse, "task_dag_json", "{}"),
            constitution_hash=getattr(synapse, "constitution_hash", ""),
            domain=getattr(synapse, "domain", "general"),
            deadline_seconds=getattr(synapse, "deadline_seconds", 3600),
        )
        result = await miner.process(delib)
        # Copy result fields back to synapse
        synapse.judgment = result.judgment
        synapse.reasoning = result.reasoning
        synapse.artifact_hash = result.artifact_hash
        synapse.dna_valid = result.dna_valid
        synapse.constitutional_hash = result.constitutional_hash
        return synapse

    axon.attach(forward_fn=_forward)
    axon.serve(netuid=args.netuid, subtensor=subtensor)
    axon.start()

    print(f"  Axon serving on port {args.port}")
    print("  Miner is running. Press Ctrl+C to stop.")

    try:
        bt.logging.info("Miner running...")
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\nShutting down miner...")
        axon.stop()
        print(f"  Final stats: {miner.stats}")


def cmd_validator(args: argparse.Namespace) -> None:
    """Start a constitutional governance validator on testnet."""
    _check_bittensor()
    import time

    import bittensor as bt

    from constitutional_swarm.bittensor.protocol import ValidatorConfig
    from constitutional_swarm.bittensor.validator import ConstitutionalValidator

    wallet = bt.wallet(name=args.wallet_name, hotkey=args.wallet_hotkey)
    subtensor = bt.subtensor(network="test")

    print(f"Starting Constitutional Validator on testnet (netuid={args.netuid})...")
    print(f"  Constitution: {args.constitution}")

    config = ValidatorConfig(
        constitution_path=args.constitution,
        peers_per_validation=args.peers,
        quorum=args.quorum,
        use_manifold=True,
    )

    validator = ConstitutionalValidator(config=config)
    print(f"  Constitution hash: {validator.constitution_hash}")

    # Register on the metagraph
    subtensor.register(wallet=wallet, netuid=args.netuid)
    metagraph = subtensor.metagraph(netuid=args.netuid)

    print(f"  Registered. Metagraph has {metagraph.n} neurons.")
    print("  Validator is running. Press Ctrl+C to stop.")

    try:
        while True:
            # Refresh metagraph
            metagraph.sync()

            # Register any new miners we discover
            for uid in range(metagraph.n):
                hotkey = metagraph.hotkeys[uid]
                if hotkey not in validator._known_miners:
                    validator.register_miner(hotkey)

            # Compute and set weights every epoch
            weights = validator.compute_emission_weights()
            if weights:
                uids = list(range(len(weights)))
                weight_values = [weights.get(metagraph.hotkeys[uid], 0.0) for uid in uids]
                subtensor.set_weights(
                    wallet=wallet,
                    netuid=args.netuid,
                    uids=uids,
                    weights=weight_values,
                )
                print(f"  Set weights for {len(weights)} miners")

            print(f"  Stats: {validator.stats}")
            time.sleep(args.epoch_seconds)

    except KeyboardInterrupt:
        print("\nShutting down validator...")
        print(f"  Final stats: {validator.stats}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Constitutional Governance Subnet - Testnet Deployment",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Register
    reg = subparsers.add_parser("register", help="Register subnet on testnet")
    reg.add_argument("--wallet-name", required=True)
    reg.add_argument("--wallet-hotkey", required=True)

    # Miner
    miner = subparsers.add_parser("miner", help="Start miner")
    miner.add_argument("--wallet-name", required=True)
    miner.add_argument("--wallet-hotkey", required=True)
    miner.add_argument("--constitution", required=True, help="Path to constitution YAML")
    miner.add_argument("--netuid", type=int, required=True)
    miner.add_argument("--port", type=int, default=8091)
    miner.add_argument("--capabilities", default="governance-judgment")
    miner.add_argument("--domains", default="general")

    # Validator
    val = subparsers.add_parser("validator", help="Start validator")
    val.add_argument("--wallet-name", required=True)
    val.add_argument("--wallet-hotkey", required=True)
    val.add_argument("--constitution", required=True, help="Path to constitution YAML")
    val.add_argument("--netuid", type=int, required=True)
    val.add_argument("--peers", type=int, default=3)
    val.add_argument("--quorum", type=int, default=2)
    val.add_argument("--epoch-seconds", type=int, default=60)

    args = parser.parse_args()

    if args.command == "register":
        cmd_register(args)
    elif args.command == "miner":
        cmd_miner(args)
    elif args.command == "validator":
        cmd_validator(args)


if __name__ == "__main__":
    main()
