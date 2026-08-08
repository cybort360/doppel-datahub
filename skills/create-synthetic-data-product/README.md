# create-synthetic-data-product

A reusable DataHub Skill for generating governed synthetic data products.

## What it does

This skill teaches an agent to:

1. Resolve a source DataHub asset.
2. Read schema, governance, ownership, domain, and lineage context.
3. Identify sensitive columns and build a typed generation plan.
4. Generate a privacy-safe synthetic twin with valid relationships.
5. Verify privacy, utility, and integrity with fail-closed decision logic.
6. Publish the twin back to DataHub with `SYNTHETIC` and `NON_PRODUCTION` tags, source lineage, scores, expiry, and evidence.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Main skill instructions and workflow |
| `templates/generation-plan.template.md` | Template for the pre-generation plan |
| `templates/evidence-report.template.md` | Template for the final evidence report |
| `references/sensitive-column-checklist.md` | Column classification guide |
| `references/verification-thresholds.md` | Default thresholds and decision logic |
| `references/datahub-aspects-used.md` | Aspects to read and write |

## Usage

Install the skill into your agent's skills directory. For example, with the Skills CLI:

```bash
npx skills add datahub-project/datahub-skills
```

Or copy this directory manually:

```bash
cp -r skills/create-synthetic-data-product  your-project/.agents/skills/
```

Then ask your agent:

> Generate a synthetic twin of `urn:li:dataset:(urn:li:dataPlatform:postgres,clinical.patients,PROD)`.

## License

Apache 2.0. See `LICENSE` in the repository root.
