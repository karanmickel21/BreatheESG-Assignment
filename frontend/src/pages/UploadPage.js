import React, { useState, useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { uploadFile, getBatches } from '../utils/api';
import { Upload, FileText, AlertTriangle, CheckCircle2, XCircle, ChevronDown, ChevronUp } from 'lucide-react';

const SOURCE_TYPES = [
  {
    id: 'sap_flat_file',
    label: 'SAP Flat File',
    description: 'SAP MM module CSV export — fuel & procurement data. Accepts German and English column headers, semicolon or comma delimiter.',
    accepts: '.csv',
    example: 'SAP_MM_FuelProcurement_Q1_2025.csv',
  },
  {
    id: 'utility_csv',
    label: 'Utility Portal CSV',
    description: 'Electricity billing export from utility portal. Handles multiple meters, overlapping billing periods, estimated reads.',
    accepts: '.csv',
    example: 'Utility_Portal_Electricity_Q1_2025.csv',
  },
  {
    id: 'travel_api',
    label: 'Corporate Travel JSON',
    description: 'Navan / Concur-style booking export. Handles flights (incl. multi-leg), hotels, ground transport. Cancelled bookings are skipped.',
    accepts: '.json',
    example: 'Navan_TravelExport_Q1_2025.json',
  },
];

function BatchRow({ batch }) {
  const [open, setOpen] = useState(false);
  const hasErrors = batch.error_log?.length > 0;

  return (
    <>
      <tr>
        <td style={{ fontSize: 12 }}>{batch.source_type_display}</td>
        <td className="mono-val" style={{ fontSize: 11 }}>{batch.source_filename || '—'}</td>
        <td>{new Date(batch.uploaded_at).toLocaleString()}</td>
        <td className="mono-val">{batch.row_count_total}</td>
        <td className="mono-val" style={{ color: 'var(--success)' }}>{batch.row_count_ok}</td>
        <td className="mono-val" style={{ color: batch.row_count_failed > 0 ? 'var(--danger)' : 'var(--text3)' }}>
          {batch.row_count_failed}
        </td>
        <td>
          <span className={`badge ${batch.status === 'completed' ? 'badge-approved' : batch.status === 'failed' ? 'badge-rejected' : 'badge-pending'}`}>
            {batch.status}
          </span>
        </td>
        <td>
          {hasErrors && (
            <button className="btn btn-ghost btn-sm" onClick={() => setOpen(v => !v)} style={{ padding: '4px 6px' }}>
              {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          )}
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={8} style={{ background: 'var(--bg3)', padding: '12px 16px' }}>
            <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 8, fontWeight: 600 }}>Parse log</div>
            {batch.error_log.map((e, i) => (
              <div key={i} style={{ marginBottom: 6, fontSize: 12 }}>
                <span style={{ color: e.severity === 'info' ? 'var(--text3)' : 'var(--danger)', marginRight: 8 }}>
                  {e.severity === 'info' ? 'ℹ' : '✗'} Row {e.row || '?'}
                </span>
                <span style={{ color: 'var(--text2)' }}>{e.error}</span>
              </div>
            ))}
          </td>
        </tr>
      )}
    </>
  );
}

export default function UploadPage() {
  const qc = useQueryClient();
  const [sourceType, setSourceType] = useState('');
  const [file, setFile] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [result, setResult] = useState(null);
  const fileRef = useRef();

  const { data: batchData } = useQuery({
    queryKey: ['batches'],
    queryFn: () => getBatches().then(r => r.data),
  });

  const upload = useMutation({
    mutationFn: () => uploadFile(sourceType, file),
    onSuccess: ({ data }) => {
      setResult({ ok: true, batch: data });
      setFile(null);
      qc.invalidateQueries(['batches']);
      qc.invalidateQueries(['dashboard']);
      qc.invalidateQueries(['records']);
    },
    onError: (err) => {
      setResult({ ok: false, message: err.response?.data?.error || 'Upload failed' });
    },
  });

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  };

  const selectedType = SOURCE_TYPES.find(s => s.id === sourceType);

  return (
    <div>
      <div className="page-header">
        <h1>Ingest Data</h1>
        <p>Upload raw source files — the parser normalises units, detects anomalies, and routes records to the review queue</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 32 }}>
        {/* Source type selector */}
        <div className="card">
          <div className="card-header"><span className="card-title">1. Select Source Type</span></div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {SOURCE_TYPES.map(st => (
              <button
                key={st.id}
                onClick={() => { setSourceType(st.id); setFile(null); setResult(null); }}
                style={{
                  padding: '14px 16px',
                  border: `1px solid ${sourceType === st.id ? 'var(--accent)' : 'var(--border2)'}`,
                  borderRadius: 8,
                  background: sourceType === st.id ? 'rgba(0,232,162,0.06)' : 'var(--bg3)',
                  color: 'var(--text)',
                  textAlign: 'left',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 4, color: sourceType === st.id ? 'var(--accent)' : 'var(--text)' }}>
                  {st.label}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text3)' }}>{st.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Upload zone */}
        <div className="card">
          <div className="card-header"><span className="card-title">2. Upload File</span></div>

          {!sourceType ? (
            <div className="empty-state" style={{ padding: 32 }}>
              <Upload size={32} />
              <p style={{ marginTop: 8 }}>Select a source type first</p>
            </div>
          ) : (
            <>
              <div
                className={`upload-zone${dragOver ? ' drag-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                <Upload />
                {file ? (
                  <>
                    <h3 style={{ color: 'var(--accent)' }}>{file.name}</h3>
                    <p>{(file.size / 1024).toFixed(1)} KB · Click to change</p>
                  </>
                ) : (
                  <>
                    <h3>Drop file or click to browse</h3>
                    <p>Accepts {selectedType?.accepts} · e.g. {selectedType?.example}</p>
                  </>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept={selectedType?.accepts}
                style={{ display: 'none' }}
                onChange={e => { setFile(e.target.files[0]); setResult(null); }}
              />

              {result && (
                <div className={`alert ${result.ok ? 'alert-success' : 'alert-error'}`} style={{ marginTop: 12 }}>
                  {result.ok ? (
                    <>
                      <CheckCircle2 size={14} style={{ display: 'inline', marginRight: 6 }} />
                      Ingested {result.batch.row_count_ok} records · {result.batch.row_count_failed} failed · {result.batch.row_count_total} total
                    </>
                  ) : (
                    <><XCircle size={14} style={{ display: 'inline', marginRight: 6 }} />{result.message}</>
                  )}
                </div>
              )}

              <button
                className="btn btn-primary"
                style={{ width: '100%', justifyContent: 'center', marginTop: 16 }}
                disabled={!file || upload.isPending}
                onClick={() => upload.mutate()}
              >
                <Upload size={14} />
                {upload.isPending ? 'Processing…' : 'Ingest File'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Validation rules info */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header"><span className="card-title">Validation Rules Applied</span></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, fontSize: 12 }}>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--scope1)', marginBottom: 8 }}>SAP Flat File</div>
            {['Duplicate PO numbers', 'Missing plant code', 'Unit variants (LTR, Liters, GAL → L)', 'Non-standard date formats', 'Quantity > 50,000 L', 'German / English headers auto-mapped'].map(r => (
              <div key={r} style={{ display: 'flex', gap: 6, marginBottom: 4, color: 'var(--text2)' }}>
                <span style={{ color: 'var(--accent)' }}>✓</span> {r}
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--scope2)', marginBottom: 8 }}>Utility CSV</div>
            {['Missing meter ID', 'Overlapping billing periods', 'Mixed unit casing (KWH, kwh, MWh)', 'Estimated readings flagged', 'Negative consumption', 'Consumption > 500 MWh threshold'].map(r => (
              <div key={r} style={{ display: 'flex', gap: 6, marginBottom: 4, color: 'var(--text2)' }}>
                <span style={{ color: 'var(--accent)' }}>✓</span> {r}
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--scope3)', marginBottom: 8 }}>Travel JSON</div>
            {['Cancelled bookings skipped (not counted)', 'Null distance → airport lookup', 'Multi-leg flights flagged', 'Same origin/destination test bookings', 'Zero-distance ground transport', 'Distance source tracked (provided/lookup/fallback)'].map(r => (
              <div key={r} style={{ display: 'flex', gap: 6, marginBottom: 4, color: 'var(--text2)' }}>
                <span style={{ color: 'var(--accent)' }}>✓</span> {r}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Batch history */}
      <div className="card">
        <div className="card-header"><span className="card-title">Ingestion History</span></div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Source</th><th>File</th><th>Uploaded</th>
                <th>Total</th><th>OK</th><th>Failed</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(batchData?.results || []).map(b => <BatchRow key={b.id} batch={b} />)}
              {(batchData?.results || []).length === 0 && (
                <tr><td colSpan={8}>
                  <div className="empty-state"><FileText size={32} /><p>No ingestion runs yet</p></div>
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
