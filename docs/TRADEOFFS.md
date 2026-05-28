# TRADEOFFS.md — Three Things Deliberately Not Built

## 1. Real-time SAP Pull (OData / RFC)

**What it would be:** Instead of file upload, a scheduler would call SAP's OData service or a BAPI via RFC to pull goods receipts directly — no manual export, no human in the loop.

**Why not built:**
Real-time SAP integration requires IT coordination that takes weeks to months at an enterprise client. You need firewall rules, a service user account, SAP Gateway activation, and in many cases sign-off from the client's SAP basis team. For a 4-day prototype demonstrating the data model and analyst UX, this is a configuration problem not a code problem.

The flat file upload path is not a placeholder — it's the actual ingestion mechanism most ESG vendors use at onboarding because it works with zero IT involvement. The architecture supports adding a pull-based connector later: `IngestionBatch.source_type` can be extended and the parser interface is source-agnostic.

**What it would take:** A Celery task scheduler, an `httpx`-based OData client with NTLM/OAuth auth, and a client-side SAP Gateway service configuration checklist. Roughly 1-2 weeks of work and 2-4 weeks of client IT coordination.

---

## 2. Market-based Scope 2 (REGO/REC Matching)

**What it would be:** Scope 2 emissions calculated using supplier-specific emission factors from renewable energy certificates (REGOs in the UK, RECs in the US, GOs in Europe) rather than the grid average.

**Why not built:**
Market-based Scope 2 requires the client to have procured REGOs/RECs and provide the associated supplier certificates and EFs. This is a separate data collection workflow — the client's energy procurement team, not the facilities team, holds this data. It also requires per-certificate matching logic (which meters are covered by which certificates, for which periods) that is non-trivial to model correctly.

The data model supports it: `EmissionRecord.scope` has a `scope2_market` value, and `EmissionFactor` can hold market-based factors. The ingestion path is not built.

**What it would take:** A certificate upload flow, a matching algorithm to associate REGOs with meter IDs and billing periods, and a residual mix fallback for uncovered consumption.

---

## 3. Automated Approval Rules / Threshold-based Auto-approval

**What it would be:** Records below a defined quantity threshold (e.g., ground transport trips < 50km, hotel stays < 2 nights) could be auto-approved without analyst review, reducing the review queue volume.

**Why not built:**
Auto-approval without human review creates audit risk. GHG Protocol Corporate Standard requires that reported figures are "accurate" and "complete" — an automated system that waves through small records could aggregate into a material number that was never actually reviewed. The point of the analyst review step is human accountability, not just data validation.

There is also a subtler risk: anomalies in small records are easier to miss precisely because they're small. A pattern of 200 ground transport bookings at 0km each would individually fall below any threshold but collectively represents a data quality problem that a human would catch.

The right long-term answer is risk-based sampling — an analyst reviews a random sample of auto-approved records and flags systematic errors. That requires a more mature QA framework than a 4-day prototype should attempt to build.

**What it would take:** A configurable threshold ruleset per category, a sampling mechanism for QA, and a governance review to agree on what "low-risk" means for this client's reporting context.
