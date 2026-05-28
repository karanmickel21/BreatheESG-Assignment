"""
python manage.py seed_demo
Seeds a demo tenant, analyst user, and sample emission records for all 3 source types.
"""

import json
import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ingestion.models import (
    Tenant, TenantMembership, IngestionBatch,
    EmissionRecord, FacilityPlant, EmissionFactor
)


class Command(BaseCommand):
    help = 'Seed demo data for BreatheESG prototype'

    def handle(self, *args, **options):
        self.stdout.write('Seeding demo data...')

        # Tenant
        tenant, _ = Tenant.objects.get_or_create(
            slug='acme-corp',
            defaults={'name': 'Acme Corporation'}
        )

        # Users
        admin_user, created = User.objects.get_or_create(
            username='analyst',
            defaults={
                'email': 'analyst@acme.com',
                'first_name': 'Priya',
                'last_name': 'Sharma',
                'is_staff': True,
            }
        )
        if created:
            admin_user.set_password('demo1234')
            admin_user.save()
        TenantMembership.objects.get_or_create(
            user=admin_user,
            defaults={'tenant': tenant, 'role': 'analyst'}
        )

        auditor_user, created = User.objects.get_or_create(
            username='auditor',
            defaults={'email': 'auditor@acme.com', 'first_name': 'Raj', 'last_name': 'Verma'}
        )
        if created:
            auditor_user.set_password('demo1234')
            auditor_user.save()
        TenantMembership.objects.get_or_create(
            user=auditor_user,
            defaults={'tenant': tenant, 'role': 'auditor'}
        )

        # Facilities
        facilities_data = [
            ('IN01', 'Mumbai Manufacturing Plant', 'IN', 'Maharashtra', 0.82),
            ('IN02', 'Delhi Office HQ', 'IN', 'Delhi', 0.82),
            ('UK01', 'London Office', 'GB', 'England', 0.23314),
            ('DE01', 'Frankfurt Warehouse', 'DE', 'Hessen', 0.366),
            ('US01', 'New York Office', 'US', 'New York', 0.386),
        ]
        facility_objs = {}
        for code, name, country, region, ef in facilities_data:
            f, _ = FacilityPlant.objects.get_or_create(
                tenant=tenant, plant_code=code,
                defaults={'name': name, 'country': country, 'region': region, 'grid_emission_factor': ef}
            )
            facility_objs[code] = f

        # Emission factors
        ef_data = [
            ('fuel_diesel', 2.68520, 'kg_co2e_per_liter', 'DEFRA 2023'),
            ('fuel_petrol', 2.31380, 'kg_co2e_per_liter', 'DEFRA 2023'),
            ('fuel_natural_gas', 2.04400, 'kg_co2e_per_liter', 'DEFRA 2023'),
            ('electricity', 0.23314, 'kg_co2e_per_kwh', 'DEFRA 2023'),
            ('travel_flight_long_haul', 0.19500, 'kg_co2e_per_km', 'DEFRA 2023'),
            ('travel_flight_short_haul', 0.15600, 'kg_co2e_per_km', 'DEFRA 2023'),
            ('travel_hotel', 31.0, 'kg_co2e_per_night', 'DEFRA 2023'),
        ]
        for activity, factor, unit, source in ef_data:
            EmissionFactor.objects.get_or_create(
                activity_type=activity,
                defaults={'factor_value': factor, 'unit': unit, 'source': source, 'valid_from': date(2023, 1, 1)}
            )

        # ----------------------------------------------------------------
        # SAP Batch
        # ----------------------------------------------------------------
        sap_batch, _ = IngestionBatch.objects.get_or_create(
            tenant=tenant,
            source_type='sap_flat_file',
            source_filename='SAP_MM_FuelProcurement_Q1_2025.csv',
            defaults={
                'status': 'completed',
                'uploaded_by': admin_user,
                'row_count_total': 45,
                'row_count_ok': 43,
                'row_count_failed': 2,
            }
        )

        sap_records = [
            # (plant_code, category, amount_liters, period_start, status, is_anomalous, anomaly_reason, doc_number, cost)
            ('IN01', 'fuel_diesel', 12500.0, date(2025, 1, 15), 'approved', False, '', '4900012301', 1250.00),
            ('IN01', 'fuel_diesel', 9800.0,  date(2025, 2, 12), 'approved', False, '', '4900012445', 980.00),
            ('IN01', 'fuel_diesel', 11200.0, date(2025, 3, 18), 'pending',  False, '', '4900012598', 1120.00),
            ('IN02', 'fuel_petrol', 3200.0,  date(2025, 1, 20), 'approved', False, '', '4900012310', 384.00),
            ('IN02', 'fuel_petrol', 2900.0,  date(2025, 2, 25), 'pending',  False, '', '4900012460', 348.00),
            ('DE01', 'fuel_diesel', 7600.0,  date(2025, 1, 8),  'approved', False, '', '4900012290', 9500.00),
            ('DE01', 'fuel_diesel', 8200.0,  date(2025, 2, 14), 'approved', False, '', '4900012435', 10250.00),
            ('DE01', 'fuel_natural_gas', 15000.0, date(2025, 1, 31), 'pending', False, '', '4900012380', 4500.00),
            ('UK01', 'fuel_petrol', 1800.0,  date(2025, 1, 10), 'approved', False, '', '4900012295', 2700.00),
            ('UK01', 'fuel_diesel', 2400.0,  date(2025, 2, 20), 'flagged',  True,
             'Quantity 20% above rolling 3-month average', '4900012455', 3600.00),
            ('IN01', 'fuel_diesel', 67000.0, date(2025, 3, 5),  'flagged',  True,
             'Quantity exceeds 50,000 L — verify SAP posting unit', '4900012570', 6700.00),
            ('US01', 'fuel_petrol', 4100.0,  date(2025, 1, 22), 'pending',  False, '', '4900012315', 7380.00),
            ('US01', 'fuel_petrol', 3900.0,  date(2025, 2, 18), 'pending',  False, '', '4900012450', 7020.00),
            ('IN01', 'fuel_lpg',    5500.0,  date(2025, 3, 10), 'pending',  False, '', '4900012580', 550.00),
        ]

        for plant_code, cat, liters, pdate, rec_status, anomalous, anomaly_reason, doc, cost in sap_records:
            ef_map = {'fuel_diesel': 2.685, 'fuel_petrol': 2.314, 'fuel_natural_gas': 2.044, 'fuel_lpg': 1.555}
            co2e = round(liters * ef_map.get(cat, 2.685), 2)
            EmissionRecord.objects.get_or_create(
                tenant=tenant,
                source_row_id=doc,
                defaults={
                    'batch': sap_batch,
                    'category': cat,
                    'scope': 'scope1',
                    'facility': facility_objs.get(plant_code),
                    'period_start': pdate,
                    'period_end': pdate,
                    'amount_raw': liters,
                    'unit_raw': 'L',
                    'amount_liters': liters,
                    'currency_raw': 'EUR' if plant_code.startswith('DE') else ('GBP' if plant_code.startswith('UK') else ('USD' if plant_code.startswith('US') else 'INR')),
                    'cost_raw': cost,
                    'co2e_kg': co2e,
                    'status': rec_status,
                    'is_anomalous': anomalous,
                    'anomaly_reason': anomaly_reason,
                    'reviewed_by': admin_user if rec_status == 'approved' else None,
                    'reviewed_at': date(2025, 4, 1) if rec_status == 'approved' else None,
                    'metadata': {
                        'plant_code': plant_code,
                        'company_code': '1000',
                        'material_code': 'FUEL_' + cat.split('_')[1].upper(),
                        'po_number': f'PO{random.randint(4500000000, 4599999999)}',
                    }
                }
            )

        # ----------------------------------------------------------------
        # Utility Batch
        # ----------------------------------------------------------------
        util_batch, _ = IngestionBatch.objects.get_or_create(
            tenant=tenant,
            source_type='utility_csv',
            source_filename='Utility_Portal_Electricity_Q1_2025.csv',
            defaults={
                'status': 'completed',
                'uploaded_by': admin_user,
                'row_count_total': 15,
                'row_count_ok': 14,
                'row_count_failed': 1,
            }
        )

        utility_records = [
            ('IN01', 'MTR-IN01-A', 245000.0, date(2025, 1, 1), date(2025, 1, 31), 'approved', False, '', 4100.0),
            ('IN01', 'MTR-IN01-B', 198000.0, date(2025, 2, 1), date(2025, 2, 28), 'approved', False, '', 3360.0),
            ('IN01', 'MTR-IN01-A', 221000.0, date(2025, 3, 1), date(2025, 3, 31), 'pending',  False, '', 3740.0),
            ('IN02', 'MTR-IN02-A', 87000.0,  date(2025, 1, 1), date(2025, 1, 31), 'approved', False, '', 1450.0),
            ('IN02', 'MTR-IN02-A', 91000.0,  date(2025, 2, 1), date(2025, 2, 28), 'pending',  False, '', 1520.0),
            ('IN02', 'MTR-IN02-A', 78000.0,  date(2025, 3, 1), date(2025, 3, 31), 'pending',  False, '', 1310.0),
            ('UK01', 'MTR-UK01',   34000.0,  date(2025, 1, 1), date(2025, 1, 31), 'approved', False, '', 6120.0),
            ('UK01', 'MTR-UK01',   29500.0,  date(2025, 2, 1), date(2025, 2, 28), 'approved', False, '', 5310.0),
            ('UK01', 'MTR-UK01',   31200.0,  date(2025, 3, 1), date(2025, 3, 31), 'pending',  False, '', 5616.0),
            ('DE01', 'MTR-DE01',   620000.0, date(2025, 1, 1), date(2025, 1, 31), 'flagged',  True,
             'Consumption > 500 MWh in single bill period — verify unit', 0.0),
            ('US01', 'MTR-US01',   125000.0, date(2025, 1, 1), date(2025, 1, 31), 'approved', False, '', 18750.0),
            ('US01', 'MTR-US01',   118000.0, date(2025, 2, 1), date(2025, 2, 28), 'pending',  False, '', 17700.0),
        ]

        for plant_code, meter_id, kwh, pstart, pend, rec_status, anomalous, anomaly, cost in utility_records:
            # Use plant-specific grid factor
            facility = facility_objs.get(plant_code)
            ef = facility.grid_emission_factor if facility else 0.233
            co2e = round(kwh * ef, 2)
            EmissionRecord.objects.get_or_create(
                tenant=tenant,
                source_row_id=meter_id + '_' + str(pstart),
                defaults={
                    'batch': util_batch,
                    'category': 'electricity',
                    'scope': 'scope2_location',
                    'facility': facility,
                    'period_start': pstart,
                    'period_end': pend,
                    'amount_raw': kwh,
                    'unit_raw': 'kWh',
                    'amount_kwh': kwh,
                    'currency_raw': 'GBP' if plant_code.startswith('UK') else ('EUR' if plant_code.startswith('DE') else ('USD' if plant_code.startswith('US') else 'INR')),
                    'cost_raw': cost,
                    'co2e_kg': co2e,
                    'status': rec_status,
                    'is_anomalous': anomalous,
                    'anomaly_reason': anomaly,
                    'reviewed_by': admin_user if rec_status == 'approved' else None,
                    'metadata': {
                        'meter_id': meter_id,
                        'site_name': facility.name if facility else '',
                        'tariff': 'Commercial HT' if plant_code.startswith('IN') else 'Non-Domestic',
                    }
                }
            )

        # ----------------------------------------------------------------
        # Travel Batch
        # ----------------------------------------------------------------
        travel_batch, _ = IngestionBatch.objects.get_or_create(
            tenant=tenant,
            source_type='travel_api',
            source_filename='Navan_TravelExport_Q1_2025.json',
            defaults={
                'status': 'completed',
                'uploaded_by': admin_user,
                'row_count_total': 35,
                'row_count_ok': 33,
                'row_count_failed': 2,
            }
        )

        travel_records = [
            # (category, amount_km/nights, period, status, source_row_id, anomalous, reason, cost, metadata)
            ('travel_flight_long_haul', 6730.0, date(2025, 1, 8),  'approved', 'PNR-AA1234', False, '', 850.0,
             {'origin': 'DEL', 'destination': 'LHR', 'airline': 'Air India', 'cabin_class': 'economy', 'passengers': 1}),
            ('travel_flight_long_haul', 6730.0, date(2025, 1, 22), 'approved', 'PNR-BA5678', False, '', 920.0,
             {'origin': 'LHR', 'destination': 'DEL', 'airline': 'British Airways', 'cabin_class': 'economy', 'passengers': 1}),
            ('travel_flight_short_haul', 631.0, date(2025, 2, 5),  'approved', 'PNR-LH9012', False, '', 310.0,
             {'origin': 'FRA', 'destination': 'LHR', 'airline': 'Lufthansa', 'cabin_class': 'economy', 'passengers': 2}),
            ('travel_flight_long_haul', 5540.0, date(2025, 2, 14), 'pending',  'PNR-VS3456', False, '', 1100.0,
             {'origin': 'LHR', 'destination': 'JFK', 'airline': 'Virgin Atlantic', 'cabin_class': 'premium_economy', 'passengers': 1}),
            ('travel_flight_domestic', 1148.0, date(2025, 1, 12), 'approved', 'PNR-6E7890', False, '', 120.0,
             {'origin': 'DEL', 'destination': 'BOM', 'airline': 'IndiGo', 'cabin_class': 'economy', 'passengers': 3}),
            ('travel_flight_domestic', 1740.0, date(2025, 3, 3),  'pending',  'PNR-AI2345', False, '', 180.0,
             {'origin': 'DEL', 'destination': 'BLR', 'airline': 'Air India', 'cabin_class': 'economy', 'passengers': 1}),
            ('travel_flight_long_haul', 10841.0, date(2025, 3, 10), 'pending', 'PNR-SQ6789', False, '', 1450.0,
             {'origin': 'LHR', 'destination': 'SIN', 'airline': 'Singapore Airlines', 'cabin_class': 'business', 'passengers': 1}),
            ('travel_flight_domestic', 0.0, date(2025, 2, 28), 'flagged', 'PNR-XX0001', True,
             'Origin and destination are the same airport', 200.0,
             {'origin': 'DEL', 'destination': 'DEL', 'airline': 'Unknown', 'cabin_class': 'economy', 'passengers': 1}),
            ('travel_hotel', 3.0, date(2025, 1, 8),  'approved', 'HTL-LON-001', False, '', 540.0,
             {'hotel_name': 'Hilton London Bankside', 'city': 'London', 'nights': 3}),
            ('travel_hotel', 5.0, date(2025, 2, 14), 'pending',  'HTL-NYC-002', False, '', 1200.0,
             {'hotel_name': 'Marriott New York Times Square', 'city': 'New York', 'nights': 5}),
            ('travel_hotel', 2.0, date(2025, 2, 5),  'approved', 'HTL-FRA-003', False, '', 320.0,
             {'hotel_name': 'Steigenberger Frankfurt', 'city': 'Frankfurt', 'nights': 2}),
            ('travel_hotel', 4.0, date(2025, 1, 20), 'approved', 'HTL-MUM-004', False, '', 280.0,
             {'hotel_name': 'Taj Mahal Palace Mumbai', 'city': 'Mumbai', 'nights': 4}),
            ('travel_hotel', 1.0, date(2025, 3, 10), 'pending',  'HTL-SIN-005', False, '', 350.0,
             {'hotel_name': 'Marina Bay Sands', 'city': 'Singapore', 'nights': 1}),
            ('travel_ground_taxi', 85.0,  date(2025, 1, 8),  'approved', 'GND-001', False, '', 65.0,
             {'provider': 'Uber', 'city': 'London'}),
            ('travel_ground_taxi', 42.0,  date(2025, 2, 14), 'approved', 'GND-002', False, '', 55.0,
             {'provider': 'Lyft', 'city': 'New York'}),
            ('travel_ground_rail', 312.0, date(2025, 2, 6),  'approved', 'GND-003', False, '', 145.0,
             {'provider': 'Eurostar', 'city': 'London → Paris'}),
            ('travel_ground_taxi', 0.0,   date(2025, 3, 1),  'flagged',  'GND-004', True,
             'Zero distance — check booking data', 38.0,
             {'provider': 'Ola', 'city': 'Mumbai'}),
        ]

        cat_ef = {
            'travel_flight_long_haul': 0.195,
            'travel_flight_short_haul': 0.156,
            'travel_flight_domestic': 0.255,
            'travel_hotel': 31.0,
            'travel_ground_taxi': 0.1486,
            'travel_ground_rail': 0.03549,
        }

        for cat, amount, pdate, rec_status, src_id, anomalous, anomaly, cost, meta in travel_records:
            co2e = round(amount * cat_ef.get(cat, 0.2), 2)
            unit = 'nights' if cat == 'travel_hotel' else 'km'
            field = 'amount_nights' if cat == 'travel_hotel' else 'amount_km'
            EmissionRecord.objects.get_or_create(
                tenant=tenant,
                source_row_id=src_id,
                defaults={
                    'batch': travel_batch,
                    'category': cat,
                    'scope': 'scope3',
                    'period_start': pdate,
                    'period_end': pdate,
                    'amount_raw': amount,
                    'unit_raw': unit,
                    field: amount,
                    'currency_raw': 'USD',
                    'cost_raw': cost,
                    'co2e_kg': co2e,
                    'status': rec_status,
                    'is_anomalous': anomalous,
                    'anomaly_reason': anomaly,
                    'reviewed_by': admin_user if rec_status == 'approved' else None,
                    'metadata': meta,
                }
            )

        self.stdout.write(self.style.SUCCESS(
            '\n✅ Demo data seeded!\n'
            '   Login: analyst / demo1234\n'
            '   Login: auditor / demo1234\n'
        ))
