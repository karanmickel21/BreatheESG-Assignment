# SOURCES.md

# SAP Research

I researched common SAP export approaches including:

* flat-file CSV exports
* IDoc exports
* OData APIs

For the prototype I selected CSV exports because they are common in analyst workflows and easier to normalize.

Observed characteristics:

* inconsistent date formats
* mixed units
* internal plant codes
* localized column names

Potential production issues:

* schema inconsistency
* missing metadata
* encoding differences

---

# Utility Data Research

I researched how facilities teams commonly retrieve electricity consumption data.

Typical formats:

* CSV portal exports
* monthly billing reports
* utility PDFs

I selected CSV ingestion because:

* easier normalization
* more reliable than OCR
* realistic for enterprise sustainability teams

Potential production issues:

* inconsistent billing periods
* tariff complexity
* multiple meter aggregation

---

# Travel Data Research

I reviewed Concur/Navan style export structures.

Typical fields:

* airport codes
* trip categories
* booking class
* hotel stays
* ground transport

The prototype models:

* flights
* hotels
* transport categories

Potential production issues:

* incomplete distance data
* changing emission factors
* inconsistent vendor formatting
