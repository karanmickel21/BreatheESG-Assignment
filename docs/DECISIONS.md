# DECISIONS.md — Every Ambiguity Resolved

## SAP: Which Export Mechanism?

**Options considered:** IDoc (ORDERS05/MATMAS), OData service (/sap/opu/odata), BAPI (RFC), flat file (MM60/MB51 report).

**Chose:** Flat file CSV from MM60/MB51 report export.

**Why:**
- IDoc requires a middleware layer (SAP PI/PO or a dedicated IDoc parser) — not realistic for a 4-day prototype and rarely available to a new vendor without months of IT coordination
- OData requires the client to have activated the relevant SAP Gateway services — not guaranteed, and authentication is complex (SAML, OAuth, basic — varies by client SAP version)
- BAPI requires RFC connectivity and firewall rules — again, a months-long engagement for enterprise IT
- Flat file is what every SAP system can produce today with no IT involvement: an MM60 report exported to CSV. A sustainability manager can do this themselves. This is how most ESG vendors actually get SAP data at onboarding

**Tradeoff:** Flat file means no real-time pull. It's a periodic batch. Acceptable for GHG reporting which is always backward-looking.

**What I'd ask the PM:** "Is there an existing SAP integration we can leverage, or are we onboarding data manually? If real-time is a requirement, we need IT involved on day 1."

---

## SAP: Which German Column Headers to Support?

SAP's MM module ships with German-language column headers in many European client configurations. I researched the actual column names from SAP's standard MB51 and MM60 reports.

Supported German → English mappings (in `parsers.py:SAP_COLUMN_MAP`):

| German | English |
|---|---|
| Werk | Plant |
| Buchungsdatum | Posting Date |
| Belegnummer | Document Number |
| Menge | Quantity |
| Basismengeneinheit | Base Unit of Measure |
| Materialkurztext | Material Description |
| Betrag in Hauswährung | Amount in Local Currency |

**What I ignored:** MARA/MARC material master fields (plant-specific material data) — these require a separate extract and are not in a standard MB51 report.

---

## Utility: Which Ingestion Mode?

**Options considered:** PDF bill parsing, portal CSV export, utility API (where available).

**Chose:** Portal CSV export.

**Why:**
- PDF parsing is fragile and utility PDF formats vary wildly — even across billing periods from the same supplier. pdfplumber can extract tables but the layout assumptions break constantly. High maintenance cost for low reliability.
- Utility APIs exist (e.g. Green Button, ESIID APIs in the US; some UK DNOs offer APIs) but are not universally available and require utility-specific OAuth. No single standard covers India, UK, Germany, and US simultaneously.
- Portal CSV is the lowest-friction mechanism that works for every utility: the facilities team logs in, clicks "Export", uploads the file. It's what most clients actually do.

**What I'd ask the PM:** "Does the client have a preferred meter data management system (MDMS) or sub-metering platform? If they use something like Schneider EcoStruxure or Siemens Navigator, we could get a direct integration."

---

## Utility: Overlapping Billing Periods

Real utility exports frequently have overlapping billing periods — especially when a meter transitions from estimated to actual readings, or when a billing cycle doesn't align with calendar months (e.g. 15 Feb → 14 Mar).

**Decision:** The parser detects overlaps per meter ID and flags them as anomalies rather than rejecting the rows. Rejection would cause data loss; flagging routes the rows to analyst review.

---

## Travel: Which Platform?

**Options considered:** SAP Concur API, Navan (formerly TripActions) API, Egencia, BCD Travel.

**Chose:** Navan/Concur-compatible JSON shape.

**Why:** Concur is the market leader for enterprise travel management. Navan is the fastest-growing challenger. Both expose a similar booking export structure — a list of booking objects with type, dates, origin/destination, cost, and optionally distance. I modelled the JSON shape after Concur's Trip Report API and Navan's export format, both of which I researched via public documentation.

**What the sample data reflects:**
- `booking_ref` maps to Concur's `ReportID` / Navan's booking `id`
- `segment_type` maps to Concur's `SegmentType`
- Multi-leg flights are represented with a `legs` array — Navan's format does this; Concur uses individual segment rows per leg

---

## Travel: Distance Calculation

Not all travel platforms provide distance. Concur's basic tier doesn't include it. Navan provides it for flights but not always for ground transport.

**Decision hierarchy:**
1. Use `distance_km` if provided by the platform (most accurate)
2. If null, look up the airport pair in `AIRPORT_DISTANCES` table (35 common international routes)
3. If not found, use 2000km fallback and flag for analyst review

**Emission factor source:** DEFRA 2023 Greenhouse Gas Conversion Factors for Company Reporting — the authoritative UK government source, updated annually. Used passenger-km factors by haul type (domestic < 500km, short-haul < 3700km, long-haul ≥ 3700km).

---

## Travel: Cancelled Bookings

**Decision:** Cancelled bookings are skipped during parsing — they generate zero emissions. They are logged in `IngestionBatch.error_log` with `severity: info` (not `error`) so analysts can see them in the batch log without them appearing as failures.

**Why not store them?** A cancelled flight that was never flown produces no emissions. Counting it would overstate Scope 3. If an analyst wants to audit what was booked-then-cancelled, that belongs in the travel platform's own reporting, not in an emissions ledger.

---

## Anomaly Detection Threshold: 50,000 L per SAP Line

A single SAP MM goods receipt posting for 50,000+ litres of diesel is unusual for most facilities. The flag prompts analyst review — it could be:
- A legitimate large refuelling event (industrial generators, fleet depot)
- A unit error (quantity in m³ posted as litres — 3x overcount)
- A batch posting covering multiple periods

The threshold is configurable per client in a real deployment. 50,000 L (~13,200 US gallons) is ~£35k of diesel at UK prices — above any plausible petty cash threshold.

---

## Status Workflow: Why Not Boolean `approved`?

A boolean `approved` field would lose the distinction between pending (not yet seen), flagged (seen and needs rework), rejected (invalid), and locked (sent to auditor). The state machine (`pending → flagged → approved → locked`) maps directly to the analyst's actual workflow and makes status transitions explicit and auditable.

---

## Deployment: Why Render?

Render supports SQLite (via persistent disk) for simple deployments and Postgres for production. Free tier is sufficient for a prototype. Railway and Fly are equivalent choices — Render was chosen for simplicity of `render.yaml` configuration.

---

## What I Would Ask the PM

1. **Reporting period:** Is the client on a calendar year or financial year for GHG reporting? This affects how we aggregate period_start/period_end across batches.

2. **Market-based Scope 2:** Does the client have any renewable energy certificates (REGOs/RECs)? If yes, we need to support market-based Scope 2 alongside location-based.

3. **SAP integration maturity:** Can the client's SAP team give us read access to an OData service, or are we always going to be working with manual flat file exports?

4. **Audit standard:** Which standard are they reporting to — GHG Protocol Corporate Standard, ISO 14064, or a specific disclosure framework (CDP, TCFD, CSRD)? This affects what the locked output needs to contain.

5. **Historical data:** Do they need to ingest historical years or only forward from onboarding? Historical ingestion often reveals data quality issues that weren't visible in current-year data.
