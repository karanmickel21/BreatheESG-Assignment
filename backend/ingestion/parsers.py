"""
BreatheESG — Ingestion Parsers
================================
Three parsers, one per data source.  Each returns a list of dicts in a
normalised shape ready to be bulk-created as EmissionRecord instances.

Design decisions documented in DECISIONS.md:
- SAP: flat-file CSV (IDoc segment ZMMR_FUEL_CONSUMPTION), not OData/BAPI
- Utility: portal CSV export (most common mechanism for facilities teams)
- Travel: Navan/Concur-style JSON (closest to real API response shape)
"""

import csv
import io
import json
import math
from datetime import date, datetime
from dateutil import parser as dateparser


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

UNIT_TO_LITERS = {
    'l': 1.0, 'liter': 1.0, 'liters': 1.0, 'liter(s)': 1.0,
    'litre': 1.0, 'litres': 1.0,
    'l_': 1.0,          # SAP sometimes appends underscore
    'gal': 3.78541,     # US gallon
    'gallon': 3.78541,
    'm3': 1000.0,       # cubic metre → litres
    'cbm': 1000.0,
    'kg': None,         # handled separately per fuel type
}

UNIT_TO_KWH = {
    'kwh': 1.0,
    'mwh': 1000.0,
    'gwh': 1_000_000.0,
    'kj': 0.000277778,
    'mj': 0.277778,
    'gj': 277.778,
}

# DEFRA 2023 emission factors (kgCO2e per unit)
EMISSION_FACTORS = {
    'fuel_diesel':            {'factor': 2.68520, 'unit': 'kg_co2e_per_liter'},
    'fuel_petrol':            {'factor': 2.31380, 'unit': 'kg_co2e_per_liter'},
    'fuel_natural_gas':       {'factor': 2.04400, 'unit': 'kg_co2e_per_liter'},  # per litre LNG equiv
    'fuel_lpg':               {'factor': 1.55540, 'unit': 'kg_co2e_per_liter'},
    'electricity':            {'factor': 0.23314, 'unit': 'kg_co2e_per_kwh'},   # UK grid avg; override per plant
    'travel_flight_domestic': {'factor': 0.25500, 'unit': 'kg_co2e_per_km'},    # per passenger-km
    'travel_flight_short_haul':{'factor': 0.15600, 'unit': 'kg_co2e_per_km'},
    'travel_flight_long_haul': {'factor': 0.19500, 'unit': 'kg_co2e_per_km'},
    'travel_hotel':           {'factor': 31.0,    'unit': 'kg_co2e_per_night'},
    'travel_ground_taxi':     {'factor': 0.14860, 'unit': 'kg_co2e_per_km'},
    'travel_ground_rail':     {'factor': 0.03549, 'unit': 'kg_co2e_per_km'},
}

# Great-circle distances (km) for common airport-pair codes.
# A real deployment would call a distances API or use a full airport DB.
AIRPORT_DISTANCES = {
    ('DEL', 'BOM'): 1148, ('BOM', 'DEL'): 1148,
    ('DEL', 'BLR'): 1740, ('BLR', 'DEL'): 1740,
    ('DEL', 'LHR'): 6730, ('LHR', 'DEL'): 6730,
    ('BOM', 'LHR'): 7189, ('LHR', 'BOM'): 7189,
    ('LHR', 'JFK'): 5540, ('JFK', 'LHR'): 5540,
    ('LHR', 'SIN'): 10841, ('SIN', 'LHR'): 10841,
    ('DEL', 'SIN'): 5630, ('SIN', 'DEL'): 5630,
    ('JFK', 'LAX'): 3983, ('LAX', 'JFK'): 3983,
    ('JFK', 'ORD'): 1190, ('ORD', 'JFK'): 1190,
    ('FRA', 'LHR'): 631,  ('LHR', 'FRA'): 631,
    ('FRA', 'JFK'): 6196, ('JFK', 'FRA'): 6196,
    ('CDG', 'LHR'): 341,  ('LHR', 'CDG'): 341,
}

SCOPE_FOR_CATEGORY = {
    'fuel_diesel': 'scope1',
    'fuel_petrol': 'scope1',
    'fuel_natural_gas': 'scope1',
    'fuel_lpg': 'scope1',
    'electricity': 'scope2_location',
    'travel_flight_domestic': 'scope3',
    'travel_flight_short_haul': 'scope3',
    'travel_flight_long_haul': 'scope3',
    'travel_hotel': 'scope3',
    'travel_ground_taxi': 'scope3',
    'travel_ground_rail': 'scope3',
    'procurement_goods': 'scope3',
    'procurement_services': 'scope3',
}


def _normalise_unit(raw_unit: str) -> str:
    return raw_unit.strip().lower().replace(' ', '')


def _parse_date(raw: str) -> date:
    """Tolerant date parser — handles DD.MM.YYYY (SAP), YYYY-MM-DD, MM/DD/YYYY etc."""
    raw = str(raw).strip()
    # SAP German format DD.MM.YYYY
    if len(raw) == 10 and raw[2] == '.' and raw[5] == '.':
        return datetime.strptime(raw, '%d.%m.%Y').date()
    return dateparser.parse(raw).date()


def _compute_co2e(category: str, normalised_amount: float) -> float:
    ef = EMISSION_FACTORS.get(category)
    if not ef or normalised_amount is None:
        return None
    return round(normalised_amount * ef['factor'], 4)


def _flight_category(origin: str, dest: str, distance_km: float) -> str:
    if distance_km < 500:
        return 'travel_flight_domestic'
    elif distance_km < 3700:
        return 'travel_flight_short_haul'
    else:
        return 'travel_flight_long_haul'


# ---------------------------------------------------------------------------
# SAP FLAT FILE PARSER
# ---------------------------------------------------------------------------
# Format chosen: SAP flat file export from MM module (Materials Management).
# Column headers may appear in German in some client configs.
# We handle both English and German header variants.
#
# Expected columns (either language):
#   BUKRS/Company Code, WERKS/Plant, BUDAT/Posting Date,
#   MATNR/Material, MENGE/Quantity, MEINS/UoM, BSTME/Order Unit,
#   EBELN/PO Number, BKTXT/Description, DMBTR/Amount, WAERS/Currency
#
# Fuel materials identified by SAP material group prefix "FUEL_" or German "KRAFT_"

SAP_COLUMN_MAP = {
    # English → canonical
    'Company Code': 'company_code',
    'Plant': 'plant_code',
    'Posting Date': 'posting_date',
    'Document Date': 'posting_date',
    'Material': 'material_code',
    'Material Description': 'material_desc',
    'Quantity': 'quantity',
    'Base Unit of Measure': 'unit',
    'Unit of Measure': 'unit',
    'UoM': 'unit',
    'PO Number': 'po_number',
    'Document Number': 'doc_number',
    'Description': 'description',
    'Amount in Local Currency': 'amount',
    'Amount': 'amount',
    'Currency': 'currency',
    # German equivalents
    'Buchungskreis': 'company_code',
    'Werk': 'plant_code',
    'Buchungsdatum': 'posting_date',
    'Belegdatum': 'posting_date',
    'Material': 'material_code',
    'Materialkurztext': 'material_desc',
    'Menge': 'quantity',
    'Basismengeneinheit': 'unit',
    'Mengeneinheit': 'unit',
    'Bestellnummer': 'po_number',
    'Belegnummer': 'doc_number',
    'Buchungstext': 'description',
    'Betrag in Hauswährung': 'amount',
    'Betrag': 'amount',
    'Währung': 'currency',
}

MATERIAL_TO_CATEGORY = {
    # material code fragment → category
    'DIESEL': 'fuel_diesel',
    'DIES': 'fuel_diesel',
    'PETROL': 'fuel_petrol',
    'GASOLINE': 'fuel_petrol',
    'BENZIN': 'fuel_petrol',
    'NATURAL_GAS': 'fuel_natural_gas',
    'ERDGAS': 'fuel_natural_gas',
    'LPG': 'fuel_lpg',
    'AUTOGAS': 'fuel_lpg',
}


def parse_sap_flat_file(file_content: str) -> list[dict]:
    """
    Parse SAP MM flat-file CSV export.
    Returns list of normalised record dicts.

    Validation checks applied:
    - Missing / null plant code → flagged
    - Duplicate PO number within file → flagged
    - Non-standard unit variants (LTR, Liters, GAL) → normalised + noted
    - Non-standard date formats (YYYY/MM/DD) → parsed + noted
    - Quantity > 50,000 L on single line → flagged
    - Unrecognised material → categorised as procurement_goods
    """
    rows = []
    errors = []

    # Detect delimiter (SAP can export with semicolon or comma)
    sample = file_content[:2000]
    delimiter = ';' if sample.count(';') > sample.count(',') else ','

    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

    # Map headers to canonical names (handles German headers automatically)
    raw_headers = reader.fieldnames or []
    header_map = {}
    for h in raw_headers:
        canonical = SAP_COLUMN_MAP.get(h.strip())
        if canonical:
            header_map[h.strip()] = canonical

    # First pass: collect all PO numbers to detect duplicates
    all_raw_rows = list(reader)
    po_seen = {}  # po_number → first doc number seen
    for raw_row in all_raw_rows:
        row = {header_map.get(k.strip(), k.strip()): (v or '').strip() for k, v in raw_row.items()}
        po = row.get('po_number', '')
        doc = row.get('doc_number', '')
        if po:
            if po in po_seen:
                po_seen[po] = 'DUPLICATE'
            else:
                po_seen[po] = doc

    for i, raw_row in enumerate(all_raw_rows):
        try:
            row = {header_map.get(k.strip(), k.strip()): (v or '').strip()
                   for k, v in raw_row.items()}

            # Skip header-repeat rows (SAP sometimes inserts them mid-file)
            if row.get('plant_code', '').lower() in ('plant', 'werk', 'werks'):
                continue

            quantity_str = row.get('quantity', '0').replace(',', '.')
            if not quantity_str or quantity_str == '0':
                continue

            quantity = float(quantity_str)
            unit_raw = row.get('unit', 'L').strip()
            material = (row.get('material_code', '') + ' ' + row.get('material_desc', '')).upper()

            # --- Identify fuel category ---
            category = None
            for fragment, cat in MATERIAL_TO_CATEGORY.items():
                if fragment in material:
                    category = cat
                    break
            if not category:
                category = 'procurement_goods'

            # --- Normalise unit to litres ---
            unit_norm = _normalise_unit(unit_raw)
            amount_liters = None
            unit_normalised_from = None
            if category.startswith('fuel_'):
                multiplier = UNIT_TO_LITERS.get(unit_norm)
                if multiplier:
                    amount_liters = round(quantity * multiplier, 4)
                    if unit_norm not in ('l', 'liter', 'litre'):
                        unit_normalised_from = unit_raw  # track non-standard unit

            # --- Date parsing (handles YYYY/MM/DD, DD.MM.YYYY, etc.) ---
            posting_date_raw = row.get('posting_date', '2025-01-01')
            posting_date = _parse_date(posting_date_raw)
            non_standard_date = '/' in posting_date_raw  # YYYY/MM/DD detected

            co2e = _compute_co2e(category, amount_liters) if amount_liters else None

            # --- Build anomaly flags ---
            anomalies = []
            plant_code = row.get('plant_code', '').strip()
            po_number = row.get('po_number', '')

            if not plant_code:
                anomalies.append('Missing plant code — cannot assign facility or grid emission factor')

            if po_seen.get(po_number) == 'DUPLICATE':
                anomalies.append(f'Duplicate PO number {po_number} — possible double-posting, verify in SAP')

            if unit_normalised_from:
                anomalies.append(f'Non-standard unit "{unit_normalised_from}" normalised to litres')

            if non_standard_date:
                anomalies.append(f'Non-standard date format "{posting_date_raw}" (YYYY/MM/DD) — parsed successfully')

            if amount_liters is not None and amount_liters > 50_000:
                anomalies.append('Quantity exceeds 50,000 L in single SAP posting — verify unit or split transaction')

            is_anomalous = len(anomalies) > 0
            anomaly_reason = '; '.join(anomalies)

            rows.append({
                'category': category,
                'scope': SCOPE_FOR_CATEGORY.get(category, 'scope1'),
                'period_start': posting_date,
                'period_end': posting_date,
                'amount_raw': quantity,
                'unit_raw': unit_raw,
                'amount_liters': amount_liters,
                'currency_raw': row.get('currency', ''),
                'cost_raw': float(row.get('amount', '0').replace(',', '.') or 0) or None,
                'co2e_kg': co2e,
                'source_row_id': row.get('doc_number', f'SAP-ROW-{i}'),
                'is_anomalous': is_anomalous,
                'anomaly_reason': anomaly_reason,
                'metadata': {
                    'plant_code': plant_code,
                    'company_code': row.get('company_code', ''),
                    'material_code': row.get('material_code', ''),
                    'material_desc': row.get('material_desc', ''),
                    'po_number': po_number,
                    'description': row.get('description', ''),
                    'unit_raw': unit_raw,
                    'date_raw': posting_date_raw,
                },
                '_parse_ok': True,
            })

        except Exception as e:
            errors.append({'row': i + 2, 'error': str(e), 'raw': str(raw_row)})
            rows.append({'_parse_ok': False, '_error': str(e), '_row': i + 2})

    return rows, errors


# ---------------------------------------------------------------------------
# UTILITY CSV PARSER
# ---------------------------------------------------------------------------
# Format: Portal CSV export (National Grid, Octopus, or similar UK/IN utility).
# Columns: Meter ID, Site Name, Billing Period Start, Billing Period End,
#          Consumption (kWh or MWh), Tariff, Cost (GBP/INR), Account Number

UTILITY_COLUMN_MAP = {
    'Meter ID': 'meter_id',
    'Meter Number': 'meter_id',
    'Meter Serial': 'meter_id',
    'Account Number': 'account_number',
    'Site': 'site_name',
    'Site Name': 'site_name',
    'Premise': 'site_name',
    'Location': 'site_name',
    'Billing Period Start': 'period_start',
    'Period Start': 'period_start',
    'From': 'period_start',
    'Start Date': 'period_start',
    'Billing Period End': 'period_end',
    'Period End': 'period_end',
    'To': 'period_end',
    'End Date': 'period_end',
    'Consumption': 'consumption',
    'Usage': 'consumption',
    'Units Consumed': 'consumption',
    'kWh': 'consumption',
    'Unit': 'unit',
    'Units': 'unit',
    'Consumption Unit': 'unit',
    'Tariff': 'tariff',
    'Tariff Name': 'tariff',
    'Rate': 'tariff',
    'Cost': 'cost',
    'Amount': 'cost',
    'Charge': 'cost',
    'Invoice Amount': 'cost',
    'Currency': 'currency',
}


def parse_utility_csv(file_content: str) -> tuple[list[dict], list[dict]]:
    """
    Validation checks applied:
    - Missing meter ID → flagged
    - Overlapping billing periods for same meter → flagged
    - Mixed-case unit variants (KWH, kwh, MWh) → normalised + noted
    - Estimated readings → noted in metadata, flagged for analyst review
    - Negative consumption → flagged
    - Consumption > 500 MWh in a single bill → flagged
    """
    rows = []
    errors = []

    sample = file_content[:2000]
    delimiter = ';' if sample.count(';') > sample.count(',') else ','

    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    raw_headers = reader.fieldnames or []
    header_map = {h.strip(): UTILITY_COLUMN_MAP.get(h.strip(), h.strip()) for h in raw_headers}

    all_raw_rows = list(reader)

    # First pass: collect billing periods per meter to detect overlaps
    meter_periods: dict[str, list[tuple]] = {}
    for raw_row in all_raw_rows:
        row = {header_map.get(k.strip(), k.strip()): (v or '').strip() for k, v in raw_row.items()}
        meter_id = row.get('meter_id', '').strip()
        if not meter_id:
            continue
        try:
            ps = _parse_date(row.get('period_start', ''))
            pe = _parse_date(row.get('period_end', '') or row.get('period_start', ''))
            if meter_id not in meter_periods:
                meter_periods[meter_id] = []
            meter_periods[meter_id].append((ps, pe))
        except Exception:
            pass

    def _has_overlap(meter_id: str, ps, pe) -> bool:
        periods = meter_periods.get(meter_id, [])
        for other_ps, other_pe in periods:
            if (ps, pe) == (other_ps, other_pe):
                continue
            # Overlap if periods intersect
            if ps <= other_pe and pe >= other_ps:
                return True
        return False

    for i, raw_row in enumerate(all_raw_rows):
        try:
            row = {header_map.get(k.strip(), k.strip()): (v or '').strip() for k, v in raw_row.items()}

            consumption_str = row.get('consumption', '0').replace(',', '')
            if not consumption_str:
                continue
            consumption = float(consumption_str)

            unit_raw = row.get('unit', 'kWh').strip() or 'kWh'
            unit_norm = _normalise_unit(unit_raw)
            kwh_multiplier = UNIT_TO_KWH.get(unit_norm, 1.0)
            amount_kwh = round(consumption * kwh_multiplier, 4)

            period_start = _parse_date(row.get('period_start', '2025-01-01'))
            period_end_raw = row.get('period_end', '')
            period_end = _parse_date(period_end_raw) if period_end_raw else period_start

            meter_id = row.get('meter_id', '').strip()
            reading_type = row.get('reading_type', 'Actual').strip()
            is_estimated = reading_type.lower() == 'estimated'

            co2e = _compute_co2e('electricity', amount_kwh)

            # --- Anomaly checks ---
            anomalies = []

            if not meter_id:
                anomalies.append('Missing meter ID — cannot trace back to specific supply point; check account number')

            if meter_id and _has_overlap(meter_id, period_start, period_end):
                anomalies.append(
                    f'Billing period {period_start}→{period_end} overlaps with another bill for meter {meter_id} '
                    f'— possible duplicate invoice or non-calendar billing cycle'
                )

            if unit_norm not in ('kwh',):
                anomalies.append(f'Non-standard unit casing "{unit_raw}" normalised to kWh (multiplier: {kwh_multiplier}x)')

            if is_estimated:
                anomalies.append('Estimated meter reading — actual consumption may differ; follow up for true-up bill')

            if consumption < 0:
                anomalies.append('Negative consumption — likely a credit note or reversal; verify with facilities team')

            if amount_kwh > 500_000:
                anomalies.append(
                    f'Consumption {amount_kwh:,.0f} kWh exceeds 500 MWh threshold '
                    f'— check if unit is MWh exported as kWh'
                )

            is_anomalous = len(anomalies) > 0
            anomaly_reason = '; '.join(anomalies)

            rows.append({
                'category': 'electricity',
                'scope': 'scope2_location',
                'period_start': period_start,
                'period_end': period_end,
                'amount_raw': consumption,
                'unit_raw': unit_raw,
                'amount_kwh': amount_kwh,
                'currency_raw': row.get('currency', 'GBP'),
                'cost_raw': float(row.get('cost', '0').replace(',', '').replace('£', '').replace('₹', '') or 0) or None,
                'co2e_kg': co2e,
                'source_row_id': (meter_id or f'NO-METER-ROW-{i}') + '_' + str(period_start),
                'is_anomalous': is_anomalous,
                'anomaly_reason': anomaly_reason,
                'metadata': {
                    'meter_id': meter_id,
                    'account_number': row.get('account_number', ''),
                    'site_name': row.get('site_name', ''),
                    'tariff': row.get('tariff', ''),
                    'reading_type': reading_type,
                    'peak_demand_kva': row.get('peak_demand_kva', row.get('peak demand kva', '')),
                    'unit_raw': unit_raw,
                },
                '_parse_ok': True,
            })

        except Exception as e:
            errors.append({'row': i + 2, 'error': str(e)})
            rows.append({'_parse_ok': False, '_error': str(e), '_row': i + 2})

    return rows, errors


# ---------------------------------------------------------------------------
# CORPORATE TRAVEL JSON PARSER
# ---------------------------------------------------------------------------
# Format: Navan/Concur-style JSON.  Each booking has type (flight/hotel/car)
# plus trip details.  Flight distances computed from airport codes if not given.

def parse_travel_json(raw_json: str) -> tuple[list[dict], list[dict]]:
    """
    Validation checks applied:
    - Cancelled bookings → skipped, logged as info (not an error)
    - Null/missing distance_km → estimated from airport lookup table, flagged if not found
    - Multi-leg flights (legs field present) → distance summed from each leg, flagged for review
    - Same origin/destination → flagged as test booking
    - Zero-distance ground transport → flagged
    """
    rows = []
    errors = []

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return [], [{'row': 0, 'error': f'Invalid JSON: {e}'}]

    bookings = data if isinstance(data, list) else data.get('bookings', data.get('trips', data.get('transactions', [])))

    for i, booking in enumerate(bookings):
        try:
            booking_type = booking.get('type', booking.get('segment_type', '')).lower()
            booking_ref = booking.get('booking_ref', booking.get('id', booking.get('pnr', f'TRV-{i}')))
            traveller = booking.get('employee_id', booking.get('traveller_id', ''))
            booking_status = booking.get('status', 'confirmed').lower()

            # --- Skip cancelled bookings ---
            if booking_status == 'cancelled':
                errors.append({
                    'row': i + 1,
                    'error': f'Booking {booking_ref} status=cancelled — skipped, no emissions counted',
                    'severity': 'info',
                })
                continue

            # Travel dates
            travel_date_raw = (
                booking.get('departure_date') or
                booking.get('check_in_date') or
                booking.get('travel_date') or
                booking.get('date') or
                '2025-01-01'
            )
            end_date_raw = (
                booking.get('return_date') or
                booking.get('check_out_date') or
                travel_date_raw
            )
            travel_date = _parse_date(travel_date_raw)
            end_date = _parse_date(end_date_raw)

            cost = float(booking.get('cost', booking.get('amount', booking.get('total_cost', 0))) or 0)
            currency = booking.get('currency', 'USD')

            if 'flight' in booking_type or 'air' in booking_type:
                origin = (booking.get('origin') or booking.get('from') or booking.get('departure_airport', '')).upper()[:3]
                dest = (booking.get('destination') or booking.get('to') or booking.get('arrival_airport', '')).upper()[:3]
                passengers = int(booking.get('passengers', booking.get('num_passengers', 1)) or 1)
                legs = booking.get('legs', [])
                is_multi_leg = bool(legs) or bool(booking.get('stopover'))

                # --- Distance resolution ---
                distance_km = booking.get('distance_km') or booking.get('distance')
                distance_estimated = False
                distance_unknown = False

                if distance_km is None:
                    # Try airport lookup
                    distance_km = AIRPORT_DISTANCES.get((origin, dest))
                    if distance_km:
                        distance_estimated = True  # computed, not provided
                    else:
                        # Multi-leg: try summing each leg
                        if legs:
                            leg_total = 0
                            for leg in legs:
                                parts = leg.replace(' ', '').split('-')
                                if len(parts) == 2:
                                    leg_dist = AIRPORT_DISTANCES.get((parts[0].upper(), parts[1].upper()))
                                    if leg_dist:
                                        leg_total += leg_dist
                            if leg_total > 0:
                                distance_km = leg_total
                                distance_estimated = True
                            else:
                                distance_km = 2000  # fallback median
                                distance_unknown = True
                        else:
                            distance_km = 2000
                            distance_unknown = True

                distance_km = float(distance_km)
                total_pkm = distance_km * passengers
                category = _flight_category(origin, dest, distance_km)
                co2e = _compute_co2e(category, total_pkm)

                # --- Anomaly checks ---
                anomalies = []
                if origin == dest:
                    anomalies.append(f'Origin and destination are identical ({origin}) — likely a test or data entry error')
                if distance_unknown:
                    anomalies.append(
                        f'No distance data for route {origin}→{dest} and route not in airport lookup table; '
                        f'2000km fallback applied — analyst should verify'
                    )
                elif distance_estimated:
                    anomalies.append(
                        f'Distance not provided by travel platform; computed from airport lookup ({distance_km:.0f}km)'
                    )
                if is_multi_leg:
                    anomalies.append(
                        f'Multi-leg itinerary ({booking.get("purpose", "")}); '
                        f'emissions calculated on total distance — consider splitting legs for precision'
                    )

                rows.append({
                    'category': category,
                    'scope': 'scope3',
                    'period_start': travel_date,
                    'period_end': end_date,
                    'amount_raw': distance_km,
                    'unit_raw': 'km',
                    'amount_km': total_pkm,
                    'currency_raw': currency,
                    'cost_raw': cost or None,
                    'co2e_kg': co2e,
                    'source_row_id': booking_ref,
                    'is_anomalous': len(anomalies) > 0,
                    'anomaly_reason': '; '.join(anomalies),
                    'metadata': {
                        'booking_ref': booking_ref,
                        'traveller_id': traveller,
                        'origin': origin,
                        'destination': dest,
                        'passengers': passengers,
                        'cabin_class': booking.get('cabin_class', booking.get('class', 'economy')),
                        'airline': booking.get('airline', booking.get('carrier', '')),
                        'is_multi_leg': is_multi_leg,
                        'distance_source': 'provided' if not distance_estimated else ('lookup' if not distance_unknown else 'fallback'),
                        'booking_status': booking_status,
                    },
                    '_parse_ok': True,
                })

            elif 'hotel' in booking_type or 'accommodation' in booking_type or 'lodging' in booking_type:
                nights = int(booking.get('nights', booking.get('num_nights', 1)) or 1)
                co2e = _compute_co2e('travel_hotel', nights)

                rows.append({
                    'category': 'travel_hotel',
                    'scope': 'scope3',
                    'period_start': travel_date,
                    'period_end': end_date,
                    'amount_raw': nights,
                    'unit_raw': 'nights',
                    'amount_nights': float(nights),
                    'currency_raw': currency,
                    'cost_raw': cost or None,
                    'co2e_kg': co2e,
                    'source_row_id': booking_ref,
                    'is_anomalous': False,
                    'anomaly_reason': '',
                    'metadata': {
                        'booking_ref': booking_ref,
                        'traveller_id': traveller,
                        'hotel_name': booking.get('hotel_name', booking.get('property', '')),
                        'city': booking.get('city', booking.get('location', '')),
                        'nights': nights,
                        'booking_status': booking_status,
                    },
                    '_parse_ok': True,
                })

            elif 'car' in booking_type or 'taxi' in booking_type or 'ground' in booking_type or 'rail' in booking_type or 'train' in booking_type:
                distance_km = float(booking.get('distance_km', booking.get('distance', 0)) or 0)
                sub_cat = 'travel_ground_rail' if ('rail' in booking_type or 'train' in booking_type) else 'travel_ground_taxi'
                co2e = _compute_co2e(sub_cat, distance_km) if distance_km else None

                anomalies = []
                if distance_km == 0:
                    anomalies.append('Zero distance recorded — cost was charged but no distance logged; check provider data')

                rows.append({
                    'category': sub_cat,
                    'scope': 'scope3',
                    'period_start': travel_date,
                    'period_end': end_date,
                    'amount_raw': distance_km,
                    'unit_raw': 'km',
                    'amount_km': distance_km,
                    'currency_raw': currency,
                    'cost_raw': cost or None,
                    'co2e_kg': co2e,
                    'source_row_id': booking_ref,
                    'is_anomalous': len(anomalies) > 0,
                    'anomaly_reason': '; '.join(anomalies),
                    'metadata': {
                        'booking_ref': booking_ref,
                        'traveller_id': traveller,
                        'provider': booking.get('provider', booking.get('vendor', '')),
                        'city': booking.get('city', ''),
                        'booking_status': booking_status,
                    },
                    '_parse_ok': True,
                })
            else:
                errors.append({'row': i + 1, 'error': f'Unknown booking type: {booking_type}', 'ref': booking_ref})

        except Exception as e:
            errors.append({'row': i + 1, 'error': str(e)})
            rows.append({'_parse_ok': False, '_error': str(e), '_row': i + 1})

    return rows, errors
