"""CLI for the DOPPEL agent.

    python -m app.agent --asset healthcare
    python -m app.agent --asset finance --scale 1 --seed 42

Runs the read -> reason (LLM) -> act -> write-back loop and prints the trace so
the agent's decisions are auditable.
"""

from __future__ import annotations

import argparse

from app.models import GenerateRequest
from app.services.agent import DoppelAgent


def main() -> None:
    parser = argparse.ArgumentParser(prog="doppel-agent")
    parser.add_argument("--asset", default="healthcare")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--expiry-days", type=int, default=30)
    parser.add_argument("--publish", action="store_true", default=True)
    args = parser.parse_args()

    print(f"\nDOPPEL agent · asset '{args.asset}' · seed {args.seed}\n" + "-" * 60)
    report, _plan = DoppelAgent().run(
        GenerateRequest(
            asset_id=args.asset,
            scale=args.scale,
            seed=args.seed,
            expiry_days=args.expiry_days,
            publish_after_generation=args.publish,
        ),
        emit=print,
    )
    print("-" * 60)
    print(f"Run {report.run_id}: {report.decision}")
    print(f"Artifacts: {report.output_dir}")


if __name__ == "__main__":
    main()
