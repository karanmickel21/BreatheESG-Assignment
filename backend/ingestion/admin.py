from django.contrib import admin
from .models import (
    Tenant, TenantMembership, IngestionBatch,
    EmissionRecord, EditHistory, FacilityPlant, EmissionFactor
)

admin.site.register(Tenant)
admin.site.register(TenantMembership)
admin.site.register(IngestionBatch)
admin.site.register(FacilityPlant)
admin.site.register(EmissionFactor)


@admin.register(EmissionRecord)
class EmissionRecordAdmin(admin.ModelAdmin):
    list_display = ['id', 'tenant', 'category', 'scope', 'period_start', 'co2e_kg', 'status']
    list_filter = ['tenant', 'scope', 'category', 'status', 'is_anomalous']
    search_fields = ['source_row_id', 'review_notes']


@admin.register(EditHistory)
class EditHistoryAdmin(admin.ModelAdmin):
    list_display = ['record', 'edited_by', 'edited_at', 'field_name']
    readonly_fields = ['record', 'edited_by', 'edited_at', 'field_name', 'old_value', 'new_value']
