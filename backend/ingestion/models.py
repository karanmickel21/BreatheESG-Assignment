"""
BreatheESG Data Models
======================
Designed for:
- Multi-tenancy (Tenant → Client isolation)
- Scope 1/2/3 GHG categorization
- Source-of-truth tracking (provenance per row)
- Unit normalization (everything stored in SI base units)
- Full audit trail (who approved, when, edit history)
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


# ---------------------------------------------------------------------------
# Multi-tenancy
# ---------------------------------------------------------------------------

class Tenant(models.Model):
    """
    Top-level client organisation. Every data row is scoped to a tenant.
    Analysts log in as users associated with a tenant.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class TenantMembership(models.Model):
    """Associates a Django User with a Tenant and grants a role."""
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('analyst', 'Analyst'),
        ('auditor', 'Auditor (read-only)'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='membership')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='members')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='analyst')

    def __str__(self):
        return f"{self.user.username} → {self.tenant.name} ({self.role})"


# ---------------------------------------------------------------------------
# Ingestion Batches — tracks each upload / pull event
# ---------------------------------------------------------------------------

class IngestionBatch(models.Model):
    """
    One upload or API pull event.  Every EmissionRecord points back to the
    batch that produced it, giving full source-of-truth provenance.
    """
    SOURCE_TYPE_CHOICES = [
        ('sap_flat_file', 'SAP Flat File (IDoc/CSV)'),
        ('utility_csv', 'Utility Portal CSV'),
        ('travel_api', 'Corporate Travel (Concur/Navan JSON)'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='batches')
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES)
    source_file = models.FileField(upload_to='uploads/%Y/%m/', null=True, blank=True)
    source_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    row_count_total = models.IntegerField(default=0)
    row_count_ok = models.IntegerField(default=0)
    row_count_failed = models.IntegerField(default=0)
    error_log = models.JSONField(default=list, blank=True)
    raw_metadata = models.JSONField(default=dict, blank=True)  # store original headers etc.

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.tenant.slug} | {self.source_type} | {self.uploaded_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Reference / lookup tables
# ---------------------------------------------------------------------------

class FacilityPlant(models.Model):
    """
    SAP uses plant codes (e.g. "DE01", "IN03").  This table maps them to
    real facilities with location context needed for Scope determination.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='plants')
    plant_code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=2)  # ISO 3166-1 alpha-2
    region = models.CharField(max_length=100, blank=True)
    grid_emission_factor = models.FloatField(
        null=True, blank=True,
        help_text="kgCO2e per kWh — regional electricity grid factor"
    )

    class Meta:
        unique_together = [('tenant', 'plant_code')]

    def __str__(self):
        return f"{self.plant_code} — {self.name}"


class EmissionFactor(models.Model):
    """
    Emission factors table. Source: DEFRA / IPCC / EPA.
    Stored per activity type so normalisation is consistent.
    """
    UNIT_CHOICES = [
        ('kg_co2e_per_liter', 'kgCO2e / litre'),
        ('kg_co2e_per_kwh', 'kgCO2e / kWh'),
        ('kg_co2e_per_km', 'kgCO2e / km'),
        ('kg_co2e_per_kg', 'kgCO2e / kg'),
        ('kg_co2e_per_night', 'kgCO2e / hotel night'),
    ]
    activity_type = models.CharField(max_length=100)  # e.g. "diesel", "grid_electricity_IN"
    factor_value = models.FloatField(help_text="kgCO2e per unit")
    unit = models.CharField(max_length=40, choices=UNIT_CHOICES)
    source = models.CharField(max_length=100, default='DEFRA 2023')
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.activity_type}: {self.factor_value} {self.unit}"


# ---------------------------------------------------------------------------
# Core emission record
# ---------------------------------------------------------------------------

class EmissionRecord(models.Model):
    """
    The canonical normalised row.  Every ingested data point — regardless of
    source — lands here in a consistent shape.

    Design principles:
    - amount_raw / unit_raw: exactly what came in, never mutated
    - amount_kwh / amount_liters / amount_kg: normalised to SI for computation
    - co2e_kg: the single computed output, always in kg CO2e
    - scope: GHG Protocol scope 1/2/3
    - status: analyst review workflow state machine
    - batch: provenance — which upload produced this row
    - audit fields: immutable once approved
    """

    # --- GHG Scope ---
    SCOPE_CHOICES = [
        ('scope1', 'Scope 1 — Direct'),
        ('scope2_location', 'Scope 2 — Location-based'),
        ('scope2_market', 'Scope 2 — Market-based'),
        ('scope3', 'Scope 3 — Value chain'),
    ]

    # --- Data source category ---
    CATEGORY_CHOICES = [
        # Scope 1
        ('fuel_diesel', 'Fuel — Diesel'),
        ('fuel_petrol', 'Fuel — Petrol'),
        ('fuel_natural_gas', 'Fuel — Natural Gas'),
        ('fuel_lpg', 'Fuel — LPG'),
        # Scope 2
        ('electricity', 'Electricity'),
        # Scope 3
        ('travel_flight_domestic', 'Travel — Flight (Domestic)'),
        ('travel_flight_short_haul', 'Travel — Flight (Short-haul)'),
        ('travel_flight_long_haul', 'Travel — Flight (Long-haul)'),
        ('travel_hotel', 'Travel — Hotel'),
        ('travel_ground_taxi', 'Travel — Ground (Taxi/Rideshare)'),
        ('travel_ground_rail', 'Travel — Ground (Rail)'),
        ('procurement_goods', 'Procurement — Goods'),
        ('procurement_services', 'Procurement — Services'),
    ]

    # --- Review workflow ---
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('flagged', 'Flagged — Needs Attention'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('locked', 'Locked for Audit'),
    ]

    # Primary key
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Tenancy & provenance
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='records')
    batch = models.ForeignKey(
        IngestionBatch, on_delete=models.SET_NULL,
        null=True, related_name='records',
        help_text="Which ingestion batch produced this row"
    )
    source_row_id = models.CharField(
        max_length=100, blank=True,
        help_text="Original row identifier from source system (SAP doc number, utility meter ID, travel booking ref)"
    )

    # Classification
    category = models.CharField(max_length=40, choices=CATEGORY_CHOICES)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES)
    facility = models.ForeignKey(
        FacilityPlant, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='records'
    )

    # Period
    period_start = models.DateField()
    period_end = models.DateField()

    # Raw values — immutable, exactly as received
    amount_raw = models.FloatField(help_text="Original quantity value")
    unit_raw = models.CharField(max_length=30, help_text="Original unit string, e.g. 'L', 'GAL', 'kWh', 'MWh'")
    currency_raw = models.CharField(max_length=10, blank=True)
    cost_raw = models.FloatField(null=True, blank=True)

    # Normalised quantities — computed on ingest, one will be non-null
    amount_liters = models.FloatField(null=True, blank=True, help_text="Normalised to litres (fuels)")
    amount_kwh = models.FloatField(null=True, blank=True, help_text="Normalised to kWh (electricity)")
    amount_km = models.FloatField(null=True, blank=True, help_text="Normalised to km (travel distance)")
    amount_kg = models.FloatField(null=True, blank=True, help_text="Normalised to kg (materials)")
    amount_nights = models.FloatField(null=True, blank=True, help_text="Hotel nights")

    # Computed output
    emission_factor_used = models.ForeignKey(
        EmissionFactor, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    co2e_kg = models.FloatField(null=True, blank=True, help_text="Final computed kgCO2e")

    # Source-specific metadata (varies by source type)
    metadata = models.JSONField(
        default=dict, blank=True,
        help_text="Source-specific fields: SAP plant/material codes, flight origin/dest, meter IDs, etc."
    )

    # Anomaly flags
    is_anomalous = models.BooleanField(default=False)
    anomaly_reason = models.TextField(blank=True)

    # Review workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='reviewed_records'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_edited = models.BooleanField(default=False, help_text="True if any field was manually edited post-ingest")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='locked_records'
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['tenant', 'scope']),
            models.Index(fields=['tenant', 'period_start', 'period_end']),
            models.Index(fields=['batch']),
        ]

    def __str__(self):
        return f"{self.tenant.slug} | {self.category} | {self.period_start} | {self.co2e_kg:.1f}kgCO2e"


class EditHistory(models.Model):
    """
    Immutable log of every manual edit to an EmissionRecord.
    Needed for audit defensibility.
    """
    record = models.ForeignKey(EmissionRecord, on_delete=models.CASCADE, related_name='edit_history')
    edited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    edited_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-edited_at']

    def __str__(self):
        return f"Edit: {self.record_id} | {self.field_name} @ {self.edited_at:%Y-%m-%d %H:%M}"
