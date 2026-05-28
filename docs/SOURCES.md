# SOURCES.md — Real-world Format Research

## Source 1: SAP Flat File (Fuel & Procurement)

### What I researched

SAP's Materials Management (MM) module is the primary system for tracking fuel and procurement transactions at manufacturing and logistics companies. Key reports:

- **MB51** (Material Document List): Lists all goods movements by material, plant, and date. This is the report a sustainability manager would run to extract fuel consumption.
- **MM60** (Inventory Turnover): Alternative for procurement spend analysis.

SAP exports these reports as:
- Semicolon-delimited CSV (default in European system locales)
- Comma-delimited CSV (US locale configurations)
- Column headers in the system language — German in European configs, English in US/UK configs

I specifically researched:
- MEINS (base unit of measure) field: SAP stores units as internal codes — `L` (litres), `KG` (kilograms), `M3` (cubic metres), `ST` (pieces). But when exported to CSV, the unit displays in its language-specific description, leading to `L`, `LTR`, `Liters`, `Liter` all appearing in practice.
- BUDAT vs BLDAT: SAP distinguishes posting date (BUDAT, when the transaction was financially posted) from document date (BLDAT, when the physical goods movement occurred). I use BUDAT as it's the authoritative date for financial reporting.
- Plant codes (WERKS): 4-character alphanumeric codes that are client-specific. Without a plant master lookup (which I modelled as `FacilityPlant`), a plant code is meaningless.

### What my sample data looks like and why

The sample file `SAP_MM_FuelProcurement_Q1_2025.csv` uses:
- **German column headers** (Werk, Buchungsdatum, etc.) — because the fictitious client's SAP is European-configured. This is the realistic default for any client with German or French operations.
- **Semicolon delimiter** — European SAP locale standard.
- **Mixed units**: most rows use `L` but two rows use `LTR` and `Liters` — reflecting what happens when a client has upgraded their SAP system mid-year and the unit display format changed, or when they have multiple SAP systems consolidated into one export.
- **One YYYY/MM/DD date** — a single row where the date format is non-standard, reflecting what happens when a record was manually entered or migrated from a legacy system.
- **One missing plant code** — a row where the plant field is blank, reflecting a posting that came from a cross-company transaction that didn't inherit the originating plant.
- **One duplicate PO number** — PO4500079012 appears twice with the same document number, reflecting a common SAP issue where a reversal and re-posting uses the same PO reference.
- **One >50,000 L quantity** — a suspected unit error (possibly m³ posted as litres).

### What would break in a real deployment

1. **Material classification**: My parser identifies fuel by material code prefix (FUEL_, KRAFT_, ERDGAS). A real client will have material codes like `A12345` with descriptions like `HSD` or `SKO` — the parser would need a configurable material-to-category mapping seeded from the client's SAP material master.
2. **Multi-system exports**: Large enterprises run multiple SAP systems (one per division or region). A real deployment would receive multiple files with potentially conflicting plant codes.
3. **IDoc format**: If the client can provide IDocs rather than flat files, the format is entirely different — segment-based, with EDIDC40 control records. The parser would need to be rewritten.
4. **Valuation class**: SAP's valuation class (BKLAS) would be a better basis for fuel classification than material code patterns, but it requires access to the material master (MARC table) not just the transaction export.

---

## Source 2: Utility Portal CSV (Electricity)

### What I researched

I researched how UK, Indian, German, and US utilities expose electricity consumption data to commercial customers:

- **UK**: Most UK DNOs (Distribution Network Operators) and suppliers (British Gas, EDF, Octopus) offer a portal where commercial accounts can download interval data or billing data as CSV. Format is not standardised — each supplier has their own column layout.
- **India**: MSEDCL, TPDDL, BESCOM portals offer bill download as PDF (primary) with some offering CSV for HT (High Tension) commercial accounts. The CSV format varies by DISCOM.
- **Germany**: German suppliers (E.ON, RWE, EnBW) offer CSV exports for Gewerbestrom (commercial electricity) accounts via their online portals.
- **US**: Green Button (ESPI standard) is the closest to standardisation, but adoption is uneven. Most utilities offer portal CSV exports for commercial accounts.

The common denominator across all of these: a facilities manager logging into a portal and downloading a CSV. No API authentication, no webhook. This is the realistic ingestion mode.

### What my sample data looks like and why

The sample file `Utility_Portal_Electricity_Q1_2025.csv` includes:
- **Multiple meters per site** (MTR-IN01-A and MTR-IN01-B for Mumbai) — realistic for large industrial facilities with multiple supply points.
- **Mixed unit casing** (`kWh`, `KWH`, `kwh`, `MWh`) — different facilities teams and different portal exports produce these variants.
- **Estimated readings** (Reading Type = Estimated) — real utilities estimate consumption when a meter is inaccessible or when the actual read isn't available before billing. Two rows are marked Estimated.
- **Overlapping billing period** — the UK meter (MTR-UK01) has a billing period of 2025-02-15 to 2025-03-14, which overlaps with the March calendar period. This is realistic when a meter transitions from monthly to non-calendar billing, or when a direct debit billing date shifts.
- **Missing meter ID** — one US row has a blank meter ID, reflecting what happens when a new supply point is not yet registered in the portal.
- **Peak Demand kVA column** — included but not used for CO₂e calculation. Realistic utility exports include peak demand for power factor correction billing. Demonstrates that real exports have columns the ingestion system doesn't need.

### Emission factors

Grid factors used (kgCO₂e/kWh):
- India: 0.82 (CEA 2023, India national grid)
- UK: 0.23314 (DEFRA 2023)
- Germany: 0.366 (UBA 2023, German national grid)
- US (NY): 0.386 (EPA eGRID 2022, NYUP subregion)

In a real deployment, these would be updated annually and the specific grid region would be determined by the facility's postcode/ZIP.

### What would break in a real deployment

1. **PDF bills**: Most Indian utilities primarily issue PDF bills. A real deployment would need a PDF extraction layer (pdfplumber + template matching per utility) before the CSV normalisation step.
2. **Half-hourly interval data**: Large UK commercial accounts receive half-hourly AMR data, not monthly billing summaries. A real system would need to aggregate interval data into billing periods or keep it at interval resolution.
3. **Multi-site account structures**: Large clients have complex account hierarchies (account → sub-account → meter → supply point). The simple meter ID used here doesn't capture this.
4. **Reactive power charges**: Some utility exports include reactive power (kVArh) alongside active power (kWh). This doesn't affect CO₂e but needs to be filtered without dropping the row.

---

## Source 3: Corporate Travel JSON (Concur/Navan)

### What I researched

I reviewed public documentation for:
- **SAP Concur**: Travel Report API (`/api/v3.0/expense/reports`), Trip API (`/api/travel/trip/v1.1`). Concur's format uses typed segment objects with `SegmentType` (Air, Hotel, Car, Rail).
- **Navan** (formerly TripActions): Export API and webhook format. Navan's format uses a booking list with `type` field.
- **Egencia**: Similar structure to Concur, more commonly seen in European enterprises.

Key findings from research:
- Not all platforms provide `distance_km` for flights — Concur's basic export omits it, requiring derivation from airport codes.
- Multi-leg itineraries are represented differently: Concur creates one segment row per leg; Navan includes a `legs` array on the parent booking.
- Hotel emissions are typically computed per night, not per room (the platform doesn't always know occupancy).
- Ground transport distance is frequently absent — the booking records the cost but not the route.
- Cancelled bookings remain in the export with a status flag — they must be explicitly filtered.

### What my sample data looks like and why

The sample file `Navan_TravelExport_Q1_2025.json` includes:
- **Multi-leg flight** (PNR-EK5501: DEL→DXB→LHR) with `distance_km: null` and a `legs` array — reflects the real Navan format for connecting flights where the platform knows the legs but not the total distance.
- **Cancelled booking** (PNR-6E9901) — a Bangalore→Delhi flight that was cancelled. The parser skips it and logs it as an info event, not an error.
- **Null distance** (PNR-EK5501, PNR-XX0001) — forces the airport lookup and fallback logic to activate.
- **Same origin/destination** (PNR-XX0001: DEL→DEL) — a test booking that was never removed from the export. The parser flags this.
- **Multiple currencies** (USD, GBP, EUR, INR, SGD) — realistic for a global company booking travel in local currencies.
- **Multiple transport modes** — flights (domestic, short-haul, long-haul), hotels, taxi, rail — each with different emission factors.

### What would break in a real deployment

1. **Pagination**: The Concur and Navan APIs paginate results. A single JSON export of 2,000 bookings is fine, but a quarter's worth of travel for a 5,000-person company would require multiple API calls and cursor-based pagination.
2. **Cabin class upgrades**: If an employee books economy and upgrades to business at the gate, Concur records the original booking class. The emission factor applied would be wrong. True deployed-class data requires integration with airline PNR systems.
3. **Car rental**: Car rental is a Scope 3 category but the emissions depend on the vehicle type (petrol/diesel/electric) which most travel platforms don't capture. We'd need to default to an average fleet factor.
4. **Missing airport codes**: Some bookings use IATA codes (3-letter), others use ICAO codes (4-letter), and some budget carrier bookings only include a city name. A robust system needs an airport resolution layer.
5. **Expense vs booking**: Concur mixes travel bookings (pre-trip) with expense claims (post-trip). A refunded booking shows up twice — once as a booking, once as a credit expense. De-duplication by booking reference is needed.
