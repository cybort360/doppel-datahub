from __future__ import annotations

import argparse
import json

from app.models import GenerateRequest
from app.services.pipeline import DoppelPipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="doppel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a synthetic data product")
    generate.add_argument("--asset", default="healthcare")
    generate.add_argument("--scale", type=float, default=1.0)
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--expiry-days", type=int, default=30)
    generate.add_argument("--publish", action="store_true")

    args = parser.parse_args()
    if args.command == "generate":
        report = DoppelPipeline().generate(
            GenerateRequest(
                asset_id=args.asset,
                scale=args.scale,
                seed=args.seed,
                expiry_days=args.expiry_days,
                publish_after_generation=args.publish,
            )
        )
        print(json.dumps(report.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
