from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    Tenant, TenantMembership, IngestionBatch,
    EmissionRecord, EditHistory, FacilityPlant, EmissionFactor
)


class UserSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    tenant = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'tenant']

    def get_role(self, obj):
        try:
            return obj.membership.role
        except TenantMembership.DoesNotExist:
            return None

    def get_tenant(self, obj):
        try:
            return {'id': str(obj.membership.tenant.id), 'name': obj.membership.tenant.name}
        except TenantMembership.DoesNotExist:
            return None


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['id', 'name', 'slug', 'created_at']


class IngestionBatchSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)

    class Meta:
        model = IngestionBatch
        fields = [
            'id', 'tenant', 'source_type', 'source_type_display',
            'source_filename', 'status', 'uploaded_by', 'uploaded_by_name',
            'uploaded_at', 'completed_at',
            'row_count_total', 'row_count_ok', 'row_count_failed',
            'error_log',
        ]
        read_only_fields = ['id', 'tenant', 'uploaded_by', 'uploaded_at', 'completed_at']

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name() or obj.uploaded_by.username
        return None


class EmissionRecordSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    scope_display = serializers.CharField(source='get_scope_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    facility_name = serializers.SerializerMethodField()
    batch_source = serializers.SerializerMethodField()

    class Meta:
        model = EmissionRecord
        fields = [
            'id', 'tenant', 'batch', 'batch_source', 'source_row_id',
            'category', 'category_display', 'scope', 'scope_display',
            'facility', 'facility_name',
            'period_start', 'period_end',
            'amount_raw', 'unit_raw', 'currency_raw', 'cost_raw',
            'amount_liters', 'amount_kwh', 'amount_km', 'amount_kg', 'amount_nights',
            'co2e_kg',
            'is_anomalous', 'anomaly_reason',
            'status', 'status_display',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'review_notes',
            'is_edited',
            'metadata',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'tenant', 'batch', 'source_row_id',
            'category', 'scope', 'amount_raw', 'unit_raw',
            'amount_liters', 'amount_kwh', 'amount_km', 'amount_kg', 'amount_nights',
            'co2e_kg', 'is_anomalous', 'anomaly_reason',
            'reviewed_by', 'reviewed_at',
            'created_at', 'updated_at',
        ]

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by:
            return obj.reviewed_by.get_full_name() or obj.reviewed_by.username
        return None

    def get_facility_name(self, obj):
        return obj.facility.name if obj.facility else None

    def get_batch_source(self, obj):
        if obj.batch:
            return obj.batch.get_source_type_display()
        return None


class EmissionRecordUpdateSerializer(serializers.ModelSerializer):
    """Used for analyst review actions — only mutable fields."""
    class Meta:
        model = EmissionRecord
        fields = ['status', 'review_notes']


class EditHistorySerializer(serializers.ModelSerializer):
    edited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = EditHistory
        fields = ['id', 'record', 'edited_by', 'edited_by_name', 'edited_at',
                  'field_name', 'old_value', 'new_value', 'reason']
        read_only_fields = ['id', 'edited_by', 'edited_at']

    def get_edited_by_name(self, obj):
        if obj.edited_by:
            return obj.edited_by.get_full_name() or obj.edited_by.username
        return None


class FacilityPlantSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacilityPlant
        fields = ['id', 'tenant', 'plant_code', 'name', 'country', 'region', 'grid_emission_factor']


class DashboardStatsSerializer(serializers.Serializer):
    total_records = serializers.IntegerField()
    pending = serializers.IntegerField()
    flagged = serializers.IntegerField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    locked = serializers.IntegerField()
    total_co2e_kg = serializers.FloatField()
    scope1_co2e_kg = serializers.FloatField()
    scope2_co2e_kg = serializers.FloatField()
    scope3_co2e_kg = serializers.FloatField()
    by_category = serializers.ListField()
    recent_batches = serializers.ListField()
