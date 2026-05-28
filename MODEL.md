# MODEL.md

## Overview

The application is designed as a multi-tenant ESG ingestion and analyst review platform. The goal is to normalize emissions-related activity data coming from multiple enterprise systems such as SAP exports, utility data, and travel platforms.

The backend uses Django REST Framework with relational models focused on auditability, traceability, and unit normalization.

---

# Core Models

## Tenant

Represents a client organization using the platform.

Fields:

* id
* name
* created_at

Purpose:
Supports multi-tenancy so multiple enterprise clients can use the platform independently.

---

## User

Represents analysts and reviewers.

Fields:

* username
* email
* role
* tenant_id

Purpose:
Allows analyst review and approval workflows.

---

## DataSource

Represents the origin of imported data.

Fields:

* source_type
* uploaded_by
* uploaded_at
* source_name

Examples:

* SAP Fuel Export
* Utility CSV
* Travel Platform Export

Purpose:
Tracks source-of-truth and ingestion origin.

---

## EmissionRecord

Normalized emissions activity record.

Fields:

* category
* scope
* quantity
* unit
* normalized_value
* emission_factor
* status
* source_id

Purpose:
Stores normalized emissions activity independent of original source format.

---

## AuditLog

Tracks analyst review actions.

Fields:

* action
* changed_by
* timestamp
* record_id

Purpose:
Provides audit trail for compliance and review tracking.

---

# Scope Handling

The platform supports:

* Scope 1 (fuel combustion)
* Scope 2 (electricity consumption)
* Scope 3 (business travel)

---

# Unit Normalization

Different source systems provide inconsistent units. The system normalizes:

* liters
* gallons
* kWh
* miles
* kilometers

into internally consistent units before emissions calculations.

---

# Source-of-Truth Tracking

Each record stores:

* ingestion source
* upload timestamp
* analyst review status
* audit history

This allows auditors to trace how a value entered the system.
