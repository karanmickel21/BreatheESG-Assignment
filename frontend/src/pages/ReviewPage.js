import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getRecords, approveRecord, rejectRecord, flagRecord, bulkApprove } from '../utils/api';
import { AlertTriangle, CheckCircle2, XCircle, Flag, ChevronDown, ChevronUp, Info } from 'lucide-react';

const SCOPE_LABEL = {
  scope1: 'S1', scope2_location: 'S2', scope2_market: 'S2M', scope3: 'S3'
};
const SCOPE_CLASS = {
  scope1: 'badge-scope1', scope2_location: 'badge-scope2', scope2_market: 'badge-scope2', scope3: 'badge-scope3'
};

function StatusBadge({ status }) {
  const map = {
    pending: 'badge-pending', flagged: 'badge-flagged',
    approved: 'badge-approved', rejected: 'badge-rejected', locked: 'badge-locked'
  };
  return <span className={`badge ${map[status] || ''}`}>{status}</span>;
}

function fmt(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function ActionModal({ record, action, onClose, onConfirm }) {
  const [notes, setNotes] = useState('');
  const label = action === 'approve' ? 'Approve' : action === 'reject' ? 'Reject' : 'Flag';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <h3>{label} Record</h3>
        <p style={{ color: 'var(--text2)', fontSize: 13, marginBottom: 16 }}>
          {record.source_row_id} · {record.category_display} · {fmt(record.co2e_kg)} kgCO₂e
        </p>
        {record.is_anomalous && (
          <div className="alert alert-warn" style={{ fontSize: 12 }}>
            <AlertTriangle size={12} style={{ display: 'inline', marginRight: 4 }} />
            {record.anomaly_reason}
          </div>
        )}
        <div className="form-group">
          <label>{action === 'flag' ? 'Flag reason' : 'Review notes'} (optional)</label>
          <textarea
            rows={3}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder={action === 'approve' ? 'LGTM — verified against SAP report' : 'Reason…'}
          />
        </div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button
            className={`btn ${action === 'approve' ? 'btn-approve' : action === 'reject' ? 'btn-reject' : 'btn-flag'}`}
            onClick={() => onConfirm(notes)}
          >
            {label}
          </button>
        </div>
      </div>
    </div>
  );
}

function RecordRow({ record, onAction, selected, onSelect }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr className={record.is_anomalous ? 'anomalous' : ''}>
        <td>
          <input type="checkbox" checked={selected} onChange={() => onSelect(record.id)}
            style={{ accentColor: 'var(--accent)' }} />
        </td>
        <td className="mono-val" style={{ fontSize: 11 }}>{record.source_row_id}</td>
        <td>
          <span className={`badge ${SCOPE_CLASS[record.scope] || ''}`}>{SCOPE_LABEL[record.scope]}</span>
        </td>
        <td style={{ fontSize: 12 }}>{record.category_display}</td>
        <td className="mono-val">{record.period_start}</td>
        <td className="mono-val">
          {fmt(record.amount_raw)} <span style={{ color: 'var(--text3)', fontSize: 11 }}>{record.unit_raw}</span>
        </td>
        <td className="mono-val" style={{ color: 'var(--accent)', fontWeight: 600 }}>
          {fmt(record.co2e_kg)}
        </td>
        <td>
          {record.is_anomalous && (
            <span className="tooltip-wrap">
              <AlertTriangle size={14} color="var(--danger)" />
              <span className="tooltip" style={{ width: 240, whiteSpace: 'normal' }}>
                {record.anomaly_reason}
              </span>
            </span>
          )}
        </td>
        <td><StatusBadge status={record.status} /></td>
        <td>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            {record.status !== 'locked' && record.status !== 'approved' && (
              <button className="btn btn-approve btn-sm" onClick={() => onAction(record, 'approve')}>✓</button>
            )}
            {record.status !== 'locked' && record.status !== 'rejected' && (
              <button className="btn btn-reject btn-sm" onClick={() => onAction(record, 'reject')}>✗</button>
            )}
            {record.status !== 'locked' && record.status !== 'flagged' && (
              <button className="btn btn-flag btn-sm" onClick={() => onAction(record, 'flag')}>⚑</button>
            )}
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setExpanded(v => !v)}
              style={{ padding: '5px 6px' }}
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={11} style={{ background: 'var(--bg3)', padding: '12px 16px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, fontSize: 12 }}>
              <div>
                <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Source</div>
                <div>{record.batch_source || '—'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Facility</div>
                <div>{record.facility_name || '—'}</div>
              </div>
              <div>
                <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Period</div>
                <div>{record.period_start} → {record.period_end}</div>
              </div>
              {record.cost_raw && (
                <div>
                  <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Cost</div>
                  <div>{record.currency_raw} {fmt(record.cost_raw)}</div>
                </div>
              )}
              {record.reviewed_by_name && (
                <div>
                  <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Reviewed by</div>
                  <div>{record.reviewed_by_name} · {record.reviewed_at?.slice(0, 10)}</div>
                </div>
              )}
              {record.review_notes && (
                <div style={{ gridColumn: 'span 2' }}>
                  <div style={{ color: 'var(--text3)', marginBottom: 4 }}>Notes</div>
                  <div>{record.review_notes}</div>
                </div>
              )}
            </div>
            {record.metadata && Object.keys(record.metadata).length > 0 && (
              <details style={{ marginTop: 12 }}>
                <summary style={{ cursor: 'pointer', color: 'var(--text3)', fontSize: 11 }}>
                  <Info size={10} style={{ display: 'inline', marginRight: 4 }} />
                  Source metadata
                </summary>
                <pre style={{ marginTop: 8, fontSize: 11, color: 'var(--text2)', whiteSpace: 'pre-wrap' }}>
                  {JSON.stringify(record.metadata, null, 2)}
                </pre>
              </details>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

export default function ReviewPage() {
  const qc = useQueryClient();
  const [filters, setFilters] = useState({ status: '', scope: '', is_anomalous: '' });
  const [selected, setSelected] = useState(new Set());
  const [modal, setModal] = useState(null); // { record, action }
  const [page, setPage] = useState(1);

  const params = { page, ...Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== '')) };
  const { data, isLoading } = useQuery({
    queryKey: ['records', params],
    queryFn: () => getRecords(params).then(r => r.data),
  });

  const mutate = useMutation({
    mutationFn: ({ record, action, notes }) => {
      if (action === 'approve') return approveRecord(record.id, notes);
      if (action === 'reject') return rejectRecord(record.id, notes);
      if (action === 'flag') return flagRecord(record.id, notes);
    },
    onSuccess: () => { qc.invalidateQueries(['records']); qc.invalidateQueries(['dashboard']); setModal(null); },
  });

  const bulkMutate = useMutation({
    mutationFn: (ids) => bulkApprove(ids),
    onSuccess: () => { qc.invalidateQueries(['records']); setSelected(new Set()); },
  });

  const records = data?.results || [];
  const total = data?.count || 0;
  const pageCount = Math.ceil(total / 50);

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };
  const toggleAll = () => {
    if (selected.size === records.length) setSelected(new Set());
    else setSelected(new Set(records.map(r => r.id)));
  };

  const STATUS_FILTERS = ['', 'pending', 'flagged', 'approved', 'rejected', 'locked'];
  const SCOPE_FILTERS = [['', 'All Scopes'], ['scope1', 'Scope 1'], ['scope2_location', 'Scope 2'], ['scope3', 'Scope 3']];

  return (
    <div>
      <div className="page-header">
        <h1>Review Queue</h1>
        <p>Inspect, approve, reject, or flag emission records before audit lock</p>
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {STATUS_FILTERS.map(s => (
            <button key={s} className={`filter-chip${filters.status === s ? ' active' : ''}`}
              onClick={() => { setFilters(f => ({ ...f, status: s })); setPage(1); }}>
              {s || 'All Status'}
            </button>
          ))}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {SCOPE_FILTERS.map(([val, label]) => (
            <button key={val} className={`filter-chip${filters.scope === val ? ' active' : ''}`}
              onClick={() => { setFilters(f => ({ ...f, scope: val })); setPage(1); }}>
              {label}
            </button>
          ))}
        </div>
        <button
          className={`filter-chip${filters.is_anomalous === 'true' ? ' active' : ''}`}
          onClick={() => { setFilters(f => ({ ...f, is_anomalous: f.is_anomalous === 'true' ? '' : 'true' })); setPage(1); }}
          style={{ borderColor: filters.is_anomalous === 'true' ? 'var(--danger)' : undefined, color: filters.is_anomalous === 'true' ? 'var(--danger)' : undefined }}
        >
          <AlertTriangle size={11} style={{ display: 'inline', marginRight: 4 }} />
          Flagged only
        </button>

        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {selected.size > 0 && (
            <button className="btn btn-approve btn-sm" onClick={() => bulkMutate.mutate([...selected])}>
              <CheckCircle2 size={13} /> Approve {selected.size} selected
            </button>
          )}
          <span style={{ fontSize: 12, color: 'var(--text3)', alignSelf: 'center' }}>
            {total} records
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: 48, textAlign: 'center' }}><div className="spinner" style={{ margin: 'auto' }} /></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th><input type="checkbox" checked={selected.size === records.length && records.length > 0} onChange={toggleAll} style={{ accentColor: 'var(--accent)' }} /></th>
                  <th>Source ID</th>
                  <th>Scope</th>
                  <th>Category</th>
                  <th>Period</th>
                  <th>Amount</th>
                  <th>kgCO₂e</th>
                  <th>⚑</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {records.map(r => (
                  <RecordRow
                    key={r.id}
                    record={r}
                    selected={selected.has(r.id)}
                    onSelect={toggleSelect}
                    onAction={(rec, action) => setModal({ record: rec, action })}
                  />
                ))}
                {records.length === 0 && (
                  <tr><td colSpan={10}>
                    <div className="empty-state">
                      <CheckCircle2 size={36} />
                      <p>No records match current filters</p>
                    </div>
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="pagination">
          <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>Previous</button>
          <span style={{ fontSize: 13, color: 'var(--text2)' }}>Page {page} of {pageCount}</span>
          <button className="btn btn-ghost btn-sm" disabled={page === pageCount} onClick={() => setPage(p => p + 1)}>Next</button>
        </div>
      )}

      {/* Action Modal */}
      {modal && (
        <ActionModal
          record={modal.record}
          action={modal.action}
          onClose={() => setModal(null)}
          onConfirm={(notes) => mutate.mutate({ record: modal.record, action: modal.action, notes })}
        />
      )}
    </div>
  );
}
