# DECISIONS.md

# SAP Source Handling

I chose CSV-based SAP exports instead of direct SAP APIs.

Reason:

* easier prototype implementation
* realistic for enterprise analyst workflows
* common in sustainability reporting teams

I assumed SAP exports would contain:

* inconsistent units
* plant codes
* mixed date formats

I ignored:

* real SAP authentication
* OData/BAPI integrations

---

# Utility Data Handling

I selected CSV utility exports instead of PDF parsing.

Reason:

* facilities teams commonly export monthly CSV usage reports
* PDF OCR would increase complexity significantly

The ingestion flow supports:

* billing periods
* tariff information
* meter consumption values

I ignored:

* OCR extraction
* utility-specific APIs

---

# Travel Data Handling

I modeled travel data after Concur/Navan export formats.

Supported:

* flights
* hotels
* ground transport

Reason:
Travel emissions commonly depend on trip category and distance.

I ignored:

* OAuth integrations
* live booking APIs
* airline-specific calculations

---

# Analyst Workflow

I implemented an analyst review dashboard so records can:

* be reviewed
* flagged
* approved

Reason:
Auditable approval flows are critical in ESG reporting.

---

# Frontend Decisions

React was selected because:

* component-based UI works well for dashboards
* easy API integration with Django REST backend

---

# Questions for PM

If more time was available, I would ask:

* expected ingestion volume
* preferred audit retention duration
* whether utility PDF ingestion is required
* whether real SAP integration is expected
