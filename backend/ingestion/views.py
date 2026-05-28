"""
BreatheESG API Views
"""

import json
from datetime import timezone as dt_timezone

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum, Count, Q
from django.utils import timezone

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Tenant, TenantMembership, IngestionBatch,
    EmissionRecord, EditHistory, FacilityPlant
)
from .serializers import (
    UserSerializer, TenantSerializer, IngestionBatchSerializer,
    EmissionRecordSerializer, EmissionRecordUpdateSerializer,
    EditHistorySerializer, FacilityPlantSerializer,
)
from .parsers import parse_sap_flat_file, parse_utility_csv, parse_travel_json


# ---------------------------------------------------------------------------
# Helper: get tenant for current user
# ---------------------------------------------------------------------------

def get_tenant(request):
    try:
        return request.user.membership.tenant
    except TenantMembership.DoesNotExist:
        return None


# ---------------------------------------------------------------------------
# Auth / User
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard(request):
    tenant = get_tenant(request)
    if not tenant:
        return Response({'error': 'No tenant associated'}, status=400)

    qs = EmissionRecord.objects.filter(tenant=tenant)

    # Status counts
    status_counts = qs.values('status').annotate(count=Count('id'))
    status_map = {s['status']: s['count'] for s in status_counts}

    # CO2e by scope
    def scope_co2e(scope_prefix):
        val = qs.filter(scope__startswith=scope_prefix).aggregate(total=Sum('co2e_kg'))['total']
        return round(val or 0, 2)

    total_co2e = round(qs.aggregate(total=Sum('co2e_kg'))['total'] or 0, 2)

    # By category
    by_cat = (
        qs.values('category')
          .annotate(total_co2e=Sum('co2e_kg'), count=Count('id'))
          .order_by('-total_co2e')[:10]
    )

    # Recent batches
    recent_batches = IngestionBatch.objects.filter(tenant=tenant).order_by('-uploaded_at')[:5]
    batch_data = IngestionBatchSerializer(recent_batches, many=True).data

    # Monthly trend (last 12 months)
    from django.db.models.functions import TruncMonth
    monthly = (
        qs.filter(co2e_kg__isnull=False)
          .annotate(month=TruncMonth('period_start'))
          .values('month')
          .annotate(total=Sum('co2e_kg'))
          .order_by('month')
    )

    return Response({
        'total_records': qs.count(),
        'pending': status_map.get('pending', 0),
        'flagged': status_map.get('flagged', 0),
        'approved': status_map.get('approved', 0),
        'rejected': status_map.get('rejected', 0),
        'locked': status_map.get('locked', 0),
        'total_co2e_kg': total_co2e,
        'scope1_co2e_kg': scope_co2e('scope1'),
        'scope2_co2e_kg': scope_co2e('scope2'),
        'scope3_co2e_kg': scope_co2e('scope3'),
        'by_category': list(by_cat),
        'recent_batches': list(batch_data),
        'monthly_trend': [
            {'month': m['month'].strftime('%Y-%m'), 'co2e_kg': round(m['total'], 2)}
            for m in monthly
        ],
    })


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class IngestionBatchViewSet(viewsets.ModelViewSet):
    serializer_class = IngestionBatchSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return IngestionBatch.objects.none()
        return IngestionBatch.objects.filter(tenant=tenant)

    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        """
        POST /api/ingestion/upload/
        Form fields:
          - source_type: sap_flat_file | utility_csv | travel_api
          - file: the uploaded file (CSV or JSON)
        """
        tenant = get_tenant(request)
        if not tenant:
            return Response({'error': 'No tenant'}, status=400)

        source_type = request.data.get('source_type')
        if source_type not in ('sap_flat_file', 'utility_csv', 'travel_api'):
            return Response({'error': 'Invalid source_type'}, status=400)

        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response({'error': 'No file provided'}, status=400)

        batch = IngestionBatch.objects.create(
            tenant=tenant,
            source_type=source_type,
            source_file=uploaded_file,
            source_filename=uploaded_file.name,
            status='processing',
            uploaded_by=request.user,
        )

        try:
            content = uploaded_file.read().decode('utf-8', errors='replace')

            if source_type == 'sap_flat_file':
                rows, errors = parse_sap_flat_file(content)
            elif source_type == 'utility_csv':
                rows, errors = parse_utility_csv(content)
            else:
                rows, errors = parse_travel_json(content)

            ok_rows = [r for r in rows if r.get('_parse_ok')]
            bad_rows = [r for r in rows if not r.get('_parse_ok')]

            with transaction.atomic():
                records_to_create = []
                for r in ok_rows:
                    r.pop('_parse_ok', None)
                    records_to_create.append(EmissionRecord(
                        tenant=tenant,
                        batch=batch,
                        status='flagged' if r.pop('is_anomalous', False) else 'pending',
                        anomaly_reason=r.pop('anomaly_reason', ''),
                        **{k: v for k, v in r.items() if not k.startswith('_')}
                    ))
                EmissionRecord.objects.bulk_create(records_to_create, batch_size=500)

            batch.status = 'completed'
            batch.row_count_total = len(rows)
            batch.row_count_ok = len(ok_rows)
            batch.row_count_failed = len(bad_rows) + len(errors)
            batch.error_log = errors[:100]  # cap stored errors
            batch.completed_at = timezone.now()
            batch.save()

            return Response(IngestionBatchSerializer(batch).data, status=201)

        except Exception as e:
            batch.status = 'failed'
            batch.error_log = [{'error': str(e)}]
            batch.save()
            return Response({'error': str(e), 'batch_id': str(batch.id)}, status=500)


# ---------------------------------------------------------------------------
# Emission Records — review dashboard
# ---------------------------------------------------------------------------

class EmissionRecordViewSet(viewsets.ModelViewSet):
    serializer_class = EmissionRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'scope', 'category', 'batch', 'is_anomalous']
    search_fields = ['source_row_id', 'metadata', 'review_notes']
    ordering_fields = ['period_start', 'co2e_kg', 'created_at', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return EmissionRecord.objects.none()
        return EmissionRecord.objects.filter(tenant=tenant).select_related(
            'batch', 'facility', 'reviewed_by'
        )

    def get_serializer_class(self):
        if self.action in ('partial_update', 'update'):
            return EmissionRecordUpdateSerializer
        return EmissionRecordSerializer

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        record = self.get_object()
        if record.status == 'locked':
            return Response({'error': 'Record is locked for audit'}, status=400)
        record.status = 'approved'
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_notes = request.data.get('notes', '')
        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        record = self.get_object()
        if record.status == 'locked':
            return Response({'error': 'Record is locked for audit'}, status=400)
        record.status = 'rejected'
        record.reviewed_by = request.user
        record.reviewed_at = timezone.now()
        record.review_notes = request.data.get('notes', 'Rejected')
        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'], url_path='flag')
    def flag(self, request, pk=None):
        record = self.get_object()
        record.status = 'flagged'
        record.anomaly_reason = request.data.get('reason', record.anomaly_reason)
        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=True, methods=['post'], url_path='lock')
    def lock(self, request, pk=None):
        record = self.get_object()
        if record.status != 'approved':
            return Response({'error': 'Only approved records can be locked'}, status=400)
        record.status = 'locked'
        record.locked_at = timezone.now()
        record.locked_by = request.user
        record.save()
        return Response(EmissionRecordSerializer(record).data)

    @action(detail=False, methods=['post'], url_path='bulk-approve')
    def bulk_approve(self, request):
        ids = request.data.get('ids', [])
        tenant = get_tenant(request)
        qs = EmissionRecord.objects.filter(tenant=tenant, id__in=ids).exclude(status='locked')
        count = qs.update(
            status='approved',
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        return Response({'approved': count})

    @action(detail=True, methods=['get'], url_path='history')
    def history(self, request, pk=None):
        record = self.get_object()
        edits = EditHistory.objects.filter(record=record)
        return Response(EditHistorySerializer(edits, many=True).data)


class FacilityPlantViewSet(viewsets.ModelViewSet):
    serializer_class = FacilityPlantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_tenant(self.request)
        if not tenant:
            return FacilityPlant.objects.none()
        return FacilityPlant.objects.filter(tenant=tenant)
