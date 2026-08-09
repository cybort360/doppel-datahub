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

## Upstream contribution commands

To open a PR against `datahub-project/datahub-skills`:

```bash
# 1. Fork https://github.com/datahub-project/datahub-skills in the GitHub UI.
# 2. Clone your fork and enter it.
git clone https://github.com/<your-username>/datahub-skills.git
cd datahub-skills

# 3. Copy this skill into the upstream skills tree.
cp -r /path/to/doppel-datahub/skills/create-synthetic-data-product skills/

# 4. Verify the skill layout matches upstream conventions.
ls skills/create-synthetic-data-product/
# expected: SKILL.md, README.md, templates/, references/

# 5. Commit, push, and open the PR.
git checkout -b add-create-synthetic-data-product-skill
git add skills/create-synthetic-data-product/
git commit -m "Add create-synthetic-data-product skill

Teaches an agent to resolve a DataHub asset, inspect schema/governance/lineage,
identify sensitive columns, build a generation strategy, generate a privacy-safe
synthetic twin, run privacy/utility/integrity verification, fail closed when
unsafe, and publish the twin back to DataHub with lineage and evidence."
git push origin add-create-synthetic-data-product-skill

# 6. Open https://github.com/datahub-project/datahub-skills/compare/main...<your-username>:add-create-synthetic-data-product-skill
#    and submit the pull request.
```

## License

Apache 2.0. See `LICENSE` in the repository root.
