# Sensitive column classification checklist

Use this checklist to classify columns from DataHub metadata and column names.

## Direct identifiers

A column is a direct identifier if any of the following are true:

- Tagged `PII` and the field name contains: `id`, `ssn`, `email`, `phone`, `name`, `address`, `street`.
- Tagged `EMAIL` or `PERSON_NAME`.
- Glossary term hints include `Person Name`, `Email Address`, `Phone Number`, `Street Address`.
- It is the table's `primaryKey` and is also tagged `PII`.

**Handling:** replace with a synthetic surrogate or faker value. Never copy source values.

## Quasi-identifiers

A column is a quasi-identifier if:

- Tagged `QUASI_IDENTIFIER`.
- Name is `date_of_birth`, `postal_code`, `zip`, `age`, or similar.

**Handling:** generalize (date → decade, postal code → prefix) or add bounded jitter. Measure the singling-out rate in the output.

## Sensitive attributes

A column is a sensitive attribute if:

- Tagged `PHI`, `FINANCIAL`, or a domain-specific sensitive tag.
- Name contains `diagnosis`, `procedure`, `claim`, `salary`, `condition`.

**Handling:** preserve statistical distribution but do not copy individual values.

## Foreign keys

A column is a foreign key if:

- Tagged `FOREIGN_KEY`.
- Declared in `SchemaMetadata.foreignKeys`.
- Name ends with `_id` and references another table's primary key.

**Handling:** generate parent table first, then remap child values to new synthetic parent keys while preserving the cardinality shape.

## Non-sensitive columns

Columns that do not match the above can be handled with empirical distribution sampling or Gaussian-copula numeric sampling.
