import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { getDashboard } from '../utils/api';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, Cell, PieChart, Pie, Legend
} from 'recharts';
import { AlertTriangle, CheckCircle2, Clock, Lock, XCircle, Zap } from 'lucide-react';

const CATEGORY_LABELS = {
  fuel_diesel: 'Diesel', fuel_petrol: 'Petrol', fuel_natural_gas: 'Natural Gas',
  fuel_lpg: 'LPG', electricity: 'Electricity',
  travel_flight_long_haul: 'Flights (Long-haul)', travel_flight_short_haul: 'Flights (Short)',
  travel_flight_domestic: 'Flights (Domestic)', travel_hotel: 'Hotels',
  travel_ground_taxi: 'Ground (Taxi)', travel_ground_rail: 'Ground (Rail)',
  procurement_goods: 'Procurement', procurement_services: 'Services',
};

const CAT_COLORS = [
  '#00e8a2','#3b82f6','#f97316','#a855f7','#eab308',
  '#06b6d4','#ec4899','#84cc16','#f43f5e','#8b5cf6',
];

function fmt(n) {
  if (n === null || n === undefined) return '—';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'k';
  return Number(n).toFixed(1);
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div style={{ background: 'var(--bg3)', border: '1px solid var(--border2)', borderRadius: 8, padding: '10px 14px' }}>
        <p style={{ color: 'var(--text2)', marginBottom: 4, fontSize: 12 }}>{label}</p>
        {payload.map((p, i) => (
          <p key={i} style={{ color: p.color || 'var(--accent)', fontSize: 13, fontWeight: 600 }}>
            {fmt(p.value)} kgCO₂e
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function DashboardPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => getDashboard().then(r => r.data),
  });

  if (isLoading) return <div className="loader-full"><div className="spinner" /></div>;
  if (error) return <div className="alert alert-error">Failed to load dashboard</div>;

  const d = data || {};

  const scopeData = [
    { name: 'Scope 1', value: d.scope1_co2e_kg || 0, color: '#f97316' },
    { name: 'Scope 2', value: d.scope2_co2e_kg || 0, color: '#3b82f6' },
    { name: 'Scope 3', value: d.scope3_co2e_kg || 0, color: '#a855f7' },
  ];

  const catData = (d.by_category || []).map(c => ({
    name: CATEGORY_LABELS[c.category] || c.category,
    co2e: Math.round(c.total_co2e || 0),
  }));

  return (
    <div>
      <div className="page-header">
        <h1>Emissions Dashboard</h1>
        <p>Acme Corporation · Q1 2025 · GHG Protocol Scope 1, 2 &amp; 3</p>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="stat-card green">
          <div className="stat-label">Total CO₂e</div>
          <div className="stat-value">{fmt(d.total_co2e_kg)}</div>
          <div className="stat-sub">kg CO₂e</div>
        </div>
        <div className="stat-card orange">
          <div className="stat-label">Scope 1</div>
          <div className="stat-value" style={{ color: 'var(--scope1)' }}>{fmt(d.scope1_co2e_kg)}</div>
          <div className="stat-sub">Direct emissions</div>
        </div>
        <div className="stat-card blue">
          <div className="stat-label">Scope 2</div>
          <div className="stat-value" style={{ color: 'var(--scope2)' }}>{fmt(d.scope2_co2e_kg)}</div>
          <div className="stat-sub">Electricity</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label">Scope 3</div>
          <div className="stat-value" style={{ color: 'var(--scope3)' }}>{fmt(d.scope3_co2e_kg)}</div>
          <div className="stat-sub">Value chain</div>
        </div>
        <div className="stat-card warn">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Clock size={10} /> Pending
          </div>
          <div className="stat-value" style={{ color: 'var(--warn)' }}>{d.pending || 0}</div>
          <div className="stat-sub">awaiting review</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <AlertTriangle size={10} /> Flagged
          </div>
          <div className="stat-value" style={{ color: 'var(--danger)' }}>{d.flagged || 0}</div>
          <div className="stat-sub">needs attention</div>
        </div>
        <div className="stat-card green">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <CheckCircle2 size={10} /> Approved
          </div>
          <div className="stat-value" style={{ color: 'var(--success)' }}>{d.approved || 0}</div>
          <div className="stat-sub">signed off</div>
        </div>
        <div className="stat-card purple">
          <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <Lock size={10} /> Locked
          </div>
          <div className="stat-value">{d.locked || 0}</div>
          <div className="stat-sub">for audit</div>
        </div>
      </div>

      {/* Charts */}
      <div className="charts-grid">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Emissions by Category</span>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={catData} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" hide />
              <YAxis type="category" dataKey="name" width={130} tick={{ fill: 'var(--text2)', fontSize: 11 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="co2e" radius={[0, 4, 4, 0]}>
                {catData.map((_, i) => <Cell key={i} fill={CAT_COLORS[i % CAT_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Scope Distribution</span>
          </div>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={scopeData} dataKey="value" nameKey="name" cx="40%" cy="50%" outerRadius={80} innerRadius={50}>
                {scopeData.map((s, i) => <Cell key={i} fill={s.color} />)}
              </Pie>
              <Tooltip formatter={(v) => [`${fmt(v)} kgCO₂e`]} />
              <Legend iconType="square" iconSize={10} formatter={(v, e) => (
                <span style={{ color: 'var(--text2)', fontSize: 12 }}>{v}: <strong style={{ color: 'var(--text)' }}>{fmt(e.payload.value)} kg</strong></span>
              )} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {(d.monthly_trend || []).length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <span className="card-title">Monthly Trend</span>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={d.monthly_trend}>
              <XAxis dataKey="month" tick={{ fill: 'var(--text2)', fontSize: 11 }} />
              <YAxis tickFormatter={fmt} tick={{ fill: 'var(--text2)', fontSize: 11 }} width={55} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="co2e_kg" stroke="var(--accent)" strokeWidth={2} dot={{ fill: 'var(--accent)', r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent Batches */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Recent Ingestion Batches</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th><th>File</th><th>Uploaded</th>
                <th>Rows</th><th>OK</th><th>Failed</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(d.recent_batches || []).map(b => (
                <tr key={b.id}>
                  <td><span className="badge badge-pending" style={{ textTransform: 'none' }}>{b.source_type_display}</span></td>
                  <td className="mono-val">{b.source_filename || '—'}</td>
                  <td>{new Date(b.uploaded_at).toLocaleDateString()}</td>
                  <td className="mono-val">{b.row_count_total}</td>
                  <td className="mono-val" style={{ color: 'var(--success)' }}>{b.row_count_ok}</td>
                  <td className="mono-val" style={{ color: b.row_count_failed > 0 ? 'var(--danger)' : 'var(--text3)' }}>{b.row_count_failed}</td>
                  <td>
                    <span className={`badge badge-${b.status === 'completed' ? 'approved' : b.status === 'failed' ? 'rejected' : 'pending'}`}>
                      {b.status}
                    </span>
                  </td>
                </tr>
              ))}
              {(d.recent_batches || []).length === 0 && (
                <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text3)', padding: 24 }}>No batches yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
