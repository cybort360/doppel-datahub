"""DOPPEL agent: an LLM planner wrapped around the deterministic engine.

The agent does real work against the catalog:

1. **Reads** DataHub / fixture context (schema, tags, keys, lineage).
2. **Reasons** — an LLM reviews every column, classifies ambiguous ones, and
   writes a governance analysis. This is the only place the model has authority.
3. **Acts** — hands its plan to the deterministic pipeline, which generates and
   fail-closed verifies the twin. The model cannot disable a privacy/integrity
   gate; if its plan degrades the data, the run is REJECTED.
4. **Writes back** — a natural-language knowledge handoff is written into the run
   artifact (and, in live mode, becomes DataHub InstitutionalMemory) so the next
   person or agent inherits the reasoning.

If the LLM is unreachable or returns unusable output, the agent falls back to the
deterministic classification and still completes — the model is an assist, not a
dependency.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.models import DatasetContext, GenerateRequest, RunReport, SemanticType
from app.services.catalog import CatalogService
from app.services.pipeline import DoppelPipeline

ALLOWED_SEMANTIC = {t.value for t in SemanticType}

SYSTEM_PROMPT = (
    "You are a data-governance agent that plans privacy-safe synthetic data "
    "generation from catalog metadata. You never see or emit real data values — "
    "you reason only about column names, types, and governance tags. For every "
    "column you assign a semantic_type from the allowed set, so the deterministic "
    "engine knows how to synthesize it without leaking identifiers. You also write "
    "a concise governance handoff for the next engineer or agent. "
    "Respond with STRICT JSON only — no prose, no code fences."
)


class DoppelAgent:
    def __init__(self) -> None:
        self.catalog = CatalogService()
        self.pipeline = DoppelPipeline()

    # -- public ------------------------------------------------------------
    def run(
        self,
        request: GenerateRequest,
        emit: Callable[[str], None] | None = None,
    ) -> tuple[RunReport, dict[str, Any]]:
        say = emit or (lambda _m: None)

        context = self.catalog.get_asset(request.asset_id)
        say(
            f"[read]  Loaded '{context.name}' from the catalog — "
            f"{len(context.tables)} table(s), domain '{context.domain}', "
            f"owner '{context.owner}'."
        )

        plan = self._plan(context, say)
        context = self._apply_plan(context, plan, say)

        say("[act]   Handing the plan to the deterministic generate + verify engine…")
        report = self.pipeline.generate(request, context_override=context)
        say(
            f"[act]   Decision {report.decision} — privacy {report.privacy_score}, "
            f"utility {report.utility_score}, integrity {report.integrity_score}."
        )

        handoff_path = self._write_handoff(context, plan, report)
        say(f"[write] Knowledge handoff written → {handoff_path}")
        if report.decision != "VERIFIED":
            say(
                "[write] Twin was REJECTED by the fail-closed gates, so nothing "
                "unsafe is published — the handoff records why."
            )

        return report, plan

    # -- reasoning ---------------------------------------------------------
    def _plan(self, context: DatasetContext, say: Callable[[str], None]) -> dict[str, Any]:
        if not settings.opencode_api_key:
            say("[reason] No LLM key configured — using deterministic classification.")
            return {}

        payload = {
            "asset": context.name,
            "domain": context.domain,
            "tables": [
                {
                    "table": t.name,
                    "primary_key": t.primary_key,
                    "foreign_keys": [fk.model_dump() for fk in t.foreign_keys],
                    "columns": [
                        {
                            "name": c.name,
                            "dtype": c.dtype,
                            "current_semantic_type": c.semantic_type.value,
                            "tags": c.tags,
                            "description": c.description,
                        }
                        for c in t.columns
                    ],
                }
                for t in context.tables
            ],
        }
        user = (
            "Allowed semantic_type values: "
            + ", ".join(sorted(ALLOWED_SEMANTIC))
            + ".\n\nCatalog metadata:\n"
            + json.dumps(payload, indent=2)
            + "\n\nReturn JSON of this exact shape:\n"
            '{"columns":[{"table":"..","name":"..","semantic_type":"..",'
            '"rationale":".."}],"sensitive_columns":["table.column"],'
            '"relationships":["short sentence"],'
            '"handoff_summary":"2-4 sentence governance note for the next agent"}\n'
            "Keep an existing classification unless it is clearly wrong. "
            "Mark every direct or quasi identifier in sensitive_columns."
        )

        say(f"[reason] Consulting {settings.opencode_model} to review the plan…")
        try:
            content = self._llm(SYSTEM_PROMPT, user)
            plan = _extract_json(content)
        except Exception as exc:  # noqa: BLE001
            say(f"[reason] LLM unavailable ({exc}); falling back to deterministic plan.")
            return {}

        if not isinstance(plan, dict) or "columns" not in plan:
            say("[reason] LLM output unusable; falling back to deterministic plan.")
            return {}
        say(
            f"[reason] LLM reviewed {len(plan.get('columns', []))} column(s); "
            f"flagged {len(plan.get('sensitive_columns', []))} as sensitive."
        )
        return plan

    def _llm(self, system: str, user: str) -> str:
        resp = httpx.post(
            f"{settings.opencode_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.opencode_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.opencode_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 3000,
                "temperature": 0.2,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"])

    # -- acting ------------------------------------------------------------
    def _apply_plan(
        self,
        context: DatasetContext,
        plan: dict[str, Any],
        say: Callable[[str], None],
    ) -> DatasetContext:
        overrides = {
            (c.get("table"), c.get("name")): c
            for c in plan.get("columns", [])
            if isinstance(c, dict)
        }
        changed = 0
        for table in context.tables:
            for column in table.columns:
                proposal = overrides.get((table.name, column.name))
                if not proposal:
                    continue
                new_type = str(proposal.get("semantic_type", "")).strip()
                if new_type not in ALLOWED_SEMANTIC:
                    continue
                if new_type != column.semantic_type.value:
                    old = column.semantic_type.value
                    column.semantic_type = SemanticType(new_type)
                    # Derive a coherent strategy from the (possibly new) type.
                    column.strategy = self.catalog._strategy_for_semantic(
                        column.semantic_type, column.name
                    )
                    changed += 1
                    say(
                        f"[reason]   reclassified {table.name}.{column.name}: "
                        f"{old} → {new_type}"
                    )
        if changed == 0 and plan:
            say("[reason] LLM confirmed the existing classification for every column.")
        return context

    # -- writing back ------------------------------------------------------
    def _write_handoff(
        self,
        context: DatasetContext,
        plan: dict[str, Any],
        report: RunReport,
    ) -> Path:
        summary = plan.get("handoff_summary") or (
            "Deterministic classification was used (no LLM handoff available)."
        )
        sensitive = plan.get("sensitive_columns", [])
        relationships = plan.get("relationships", [])

        lines = [
            f"# DOPPEL agent handoff — run `{report.run_id}`",
            "",
            f"- Asset: **{context.name}** ({context.domain})",
            f"- Decision: **{report.decision}** "
            f"(privacy {report.privacy_score}, utility {report.utility_score}, "
            f"integrity {report.integrity_score})",
            f"- Planner: `{settings.opencode_model}` "
            f"({'LLM' if plan else 'deterministic fallback'})",
            "",
            "## Governance summary",
            "",
            summary,
            "",
        ]
        if sensitive:
            lines += ["## Sensitive columns", ""]
            lines += [f"- `{s}`" for s in sensitive]
            lines += [""]
        if relationships:
            lines += ["## Relationships preserved", ""]
            lines += [f"- {r}" for r in relationships]
            lines += [""]
        lines += [
            "## Handoff",
            "",
            "This note is the knowledge the next person or agent inherits. In live "
            "DataHub mode it is attached to each synthetic dataset as "
            "`InstitutionalMemory`; the deterministic verification gates remain the "
            "sole authority on whether the twin is safe to publish.",
            "",
        ]
        path = Path(report.output_dir, "agent_handoff.md")
        path.write_text("\n".join(lines))
        return path


def _extract_json(text: str) -> Any:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object in LLM response")
    return json.loads(text[start : end + 1])
