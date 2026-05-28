# TRADEOFFS.md

# 1. No Real SAP Integration

I intentionally avoided real SAP OData/BAPI integration.

Reason:

* requires enterprise credentials
* significantly increases implementation complexity
* outside scope of 4-day prototype

Instead, I modeled realistic SAP CSV exports.

---

# 2. No OCR for Utility PDFs

I did not implement PDF OCR extraction.

Reason:

* OCR pipelines are error-prone
* would require additional preprocessing infrastructure
* CSV utility exports are sufficient for prototype scope

---

# 3. Simplified Authentication

Authentication was simplified during deployment troubleshooting.

Reason:

* deployment stability was prioritized
* assignment focus is data modeling and ingestion workflow
* authentication can be expanded later with production-grade JWT flows
