# MODEL.md — BreatheESG Data Model

## Overview

The data model solves one core problem: **emission data comes from many sources in many shapes, and every row needs to be traceable, normalised, reviewed, and defensible to an auditor.**

Five design concerns drive every decision:

1. Multi-tenancy
2. GHG Protocol scope categorisation
3. Source-of-truth provenance per row
4. Unit normalisation
5. Audit trail

---

## Entity Map

```
Tenant
  └── TenantMembership (User ↔ Tenant, with role)
  └── FacilityPlant (SAP plant codes → real facilities)
  └── IngestionBatch (one upload/pull event)
        └── EmissionRecord (one normalised data point)
              └── EditHistory (immutable log of manual changes)
  └── EmissionFactor (DEFRA/IPCC factors, versioned by valid_from)
```

---

## Multi-tenancy

Every row in `EmissionRecord`, `IngestionBatch`, and `FacilityPlant` carries a `tenant_id` foreign key. Django queryset scoping in every view enforces isolation — a user from Tenant A can never retrieve records from Tenant B. `TenantMembership` maps users to tenants with a role (`admin`, `analyst`, `auditor`).

**Why not row-level security at the DB layer?** For a prototype with SQLite/Postgres and a Django ORM, queryset filtering is the right tradeoff — it's auditable in Python code and does not require DB-specific RLS configuration that varies across Postgres, SQLite, and hosted providers. A production system would add RLS as a second layer of defence.

---

## Scope 1/2/3 Categorisation

`EmissionRecord.scope` is an enum:

| Value | Meaning |
|---|---|
| `scope1` | Direct combustion — diesel, petrol, gas, LPG |
| `scope2_location` | Electricity on location-based method (grid average EF) |
| `scope2_market` | Electricity on market-based method (supplier EF, REGOs) |
| `scope3` | All travel, hotel, procurement upstream/downstream |

Scope is **assigned at parse time** based on `category`. The mapping is in `parsers.py:SCOPE_FOR_CATEGORY` — a deliberate single point of truth so that a change in GHG Protocol guidance only needs updating in one place.

Scope 2 is stored as `scope2_location` by default. If a client provides a market-based EF or REGO certificates, an analyst can override to `scope2_market` and the edit is logged in `EditHistory`.

---

## Source-of-Truth Tracking

Every `EmissionRecord` carries:

| Field | Purpose |
|---|---|
| `batch` | FK to `IngestionBatch` — which upload produced this row |
| `source_row_id` | Original identifier from the source system (SAP doc number, meter ID + period, booking reference) |
| `amount_raw` / `unit_raw` | Immutable — exactly what came in, never mutated |
| `metadata` (JSONField) | Source-specific fields: SAP plant/material codes, meter tariff, cabin class, airline |

The combination of `batch` + `source_row_id` makes every row uniquely traceable back to its origin. If an auditor asks "where does this 12,500 L diesel figure come from?", the answer is: `IngestionBatch(id=..., source_filename='SAP_MM_FuelProcurement_Q1_2025.csv')`, document number `4900012301`.

---

## Unit Normalisation

Raw values are stored **unchanged** in `amount_raw` + `unit_raw`. Normalised values are stored in typed columns:

| Column | Used for |
|---|---|
| `amount_liters` | Fuel quantities (diesel, petrol, gas, LPG) |
| `amount_kwh` | Electricity |
| `amount_km` | Travel distance (flight passenger-km, ground km) |
| `amount_kg` | Procurement weight |
| `amount_nights` | Hotel stays |

Exactly one of these will be non-null for any given record.

**Why separate columns instead of a generic `normalised_amount` + `normalised_unit`?**
Separate columns allow typed aggregation in SQL without string matching, and make schema-level constraints possible. A `SUM(amount_kwh)` across all electricity records is unambiguous. A `SUM(normalised_amount) WHERE normalised_unit = 'kwh'` is fragile.

**Normalisation logic** lives in `parsers.py`. Unit variant tables (`UNIT_TO_LITERS`, `UNIT_TO_KWH`) handle the real-world messiness: `L`, `LTR`, `Liters`, `KWH`, `kwh`, `MWh`, `GAL`, `M3`.

`co2e_kg` is the final computed output — always in kg CO₂e, using the emission factor from `EmissionFactor` referenced by `emission_factor_used`.

---

## Audit Trail

### Pre-lock: analyst review

```
pending → flagged → approved → locked
          ↘ rejected
```

- `status` drives the workflow state machine
- `reviewed_by` + `reviewed_at` capture who signed off and when
- `review_notes` are freetext
- `is_edited` is set True if any field is manually adjusted post-ingest
- `EditHistory` records every individual field change with old/new value and reason

### Post-lock: immutable

Once `status = locked`, the record cannot be updated via API (enforced in views). `locked_by` + `locked_at` capture the lock event. Locked records are what goes to auditors.

### Why EditHistory is a separate table, not a JSONField

A JSONField change log would require application-level diffing and is harder to query. A separate `EditHistory` row per field change is individually queryable (`SELECT * FROM edit_history WHERE record_id = ? AND field_name = 'co2e_kg'`), indexable, and survives partial record corruption.

---

## IngestionBatch

Tracks every ingest event:

- `source_type`: which parser was used
- `source_file`: the original file stored in media storage
- `row_count_total / ok / failed`: parse summary
- `error_log`: JSONField list of parse errors with row numbers
- `raw_metadata`: original headers, delimiter, etc. — useful for debugging unexpected parser failures

Batches are never deleted. If a bad file is uploaded, its batch is marked `failed` and the error_log is visible in the UI.

---

## FacilityPlant

SAP uses plant codes (`IN01`, `DE01`) that mean nothing without a lookup table. `FacilityPlant` maps these to:

- Human-readable name and country
- `grid_emission_factor` (kgCO₂e/kWh) — per-region grid factor for Scope 2 calculations

In a real deployment, this table would be pre-populated from the client's SAP organisation structure during onboarding. For this prototype it is seeded via `management/commands/seed_demo.py`.

---

## Indexes

```python
Index(fields=['tenant', 'status'])        # review queue filtering
Index(fields=['tenant', 'scope'])         # scope aggregation for dashboard
Index(fields=['tenant', 'period_start', 'period_end'])  # period-based queries
Index(fields=['batch'])                    # batch drill-down
```

The compound `(tenant, status)` index covers the most common analyst query pattern.

---

## What This Model Does Not Handle (and Why)

| Not built | Reason |
|---|---|
| Market-based Scope 2 (REGO/REC matching) | Requires supplier certificate ingestion — out of scope for 4-day prototype |
| Scope 3 Categories 1-15 full breakdown | Category 1 (purchased goods) alone requires spend-based or lifecycle modelling — a separate product decision |
| Currency conversion | Cost fields are stored in original currency. FX conversion for cross-currency aggregation requires an exchange rate feed — not needed for CO₂e calculation |
| Time-series change tracking on EmissionFactor | DEFRA updates factors annually. A `valid_from`/`valid_to` pair handles this but re-calculation of historical records on factor update is not automated |
