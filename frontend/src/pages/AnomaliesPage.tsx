import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, CheckCircle, RefreshCw, FileText } from 'lucide-react';
import { pipelineApi, type AnomalyFeedItem } from '../api/pipeline';
import { describeError } from '../api/documents';
import { formatRelative } from '../utils/formatters';

/**
 * Anomaly log — real findings from the processing pipeline.
 *
 * Every row is an anomaly the pipeline actually raised while reading an uploaded
 * document, joined back to that document and to the land record it was written
 * to. The previous version of this page rendered a fixed list, so it could not
 * show (or clear) a single finding from an actual upload.
 */

const TYPE_LABELS: Record<string, string> = {
  DUPLICATE_RECORD: 'Duplicate Record',
  AREA_MISMATCH: 'Area Mismatch',
  OWNER_CONFLICT: 'Owner Conflict',
  BOUNDARY_CONFLICT: 'Boundary Conflict',
  SURVEY_FORMAT_ERROR: 'Survey Format Error',
  MISSING_REQUIRED: 'Missing Required Field',
  LOW_CONFIDENCE_FIELD: 'Low Confidence Field',
};

const SEVERITIES = ['HIGH', 'MEDIUM', 'LOW'] as const;

function confidenceColor(pct: number): string {
  if (pct >= 85) return 'var(--color-success-600)';
  if (pct >= 65) return 'var(--color-warning-600)';
  return 'var(--color-error-600)';
}

export function AnomaliesPage() {
  const [anomalies, setAnomalies] = useState<AnomalyFeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [resolving, setResolving] = useState<string | null>(null);
  const [sevF, setSevF] = useState('');
  const [typeF, setTypeF] = useState('');
  const [statusF, setStatusF] = useState<'all' | 'open' | 'resolved'>('all');

  const load = useCallback(async () => {
    try {
      const res = await pipelineApi.listAnomalies({ page_size: 200 });
      setAnomalies(res.items);
      setError('');
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const resolve = async (id: string) => {
    setResolving(id);
    setActionError('');
    try {
      await pipelineApi.resolveAnomaly(id);
      // Reflect the server's answer rather than assuming it succeeded.
      setAnomalies(prev => prev.map(a => (a.id === id ? { ...a, resolved: true } : a)));
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setResolving(null);
    }
  };

  const stats = useMemo(() => ({
    total: anomalies.length,
    high: anomalies.filter(a => a.severity === 'HIGH').length,
    open: anomalies.filter(a => !a.resolved).length,
  }), [anomalies]);

  const filtered = useMemo(() => {
    let d = anomalies;
    if (sevF) d = d.filter(a => a.severity === sevF);
    if (typeF) d = d.filter(a => a.anomaly_type === typeF);
    if (statusF === 'open') d = d.filter(a => !a.resolved);
    if (statusF === 'resolved') d = d.filter(a => a.resolved);
    return d;
  }, [anomalies, sevF, typeF, statusF]);

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Validation &amp; Anomalies</div>
          <div className="page-hdr__sub">Inconsistencies the pipeline found while reading uploaded documents</div>
        </div>
        <button className="btn btn--secondary btn--sm" onClick={() => { void load(); }}>
          <RefreshCw size={13} className={loading ? 'spin' : ''}/> Refresh
        </button>
      </div>

      {(error || actionError) && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          {error || actionError}
        </div>
      )}

      {/* Summary KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 'var(--space-4)', marginBottom: 'var(--space-5)' }}>
        {[
          { label: 'Total Anomalies', value: stats.total, color: '#EFF6FF', accent: '#2563EB' },
          { label: 'High Severity', value: stats.high, color: '#FEF2F2', accent: '#DC2626' },
          { label: 'Open / Unresolved', value: stats.open, color: '#FEF3C7', accent: '#D97706' },
        ].map(k => (
          <div key={k.label} className="kpi">
            <div className="kpi__accent" style={{ background: k.accent }}/>
            <div className="kpi__value">{k.value}</div>
            <div className="kpi__label">{k.label}</div>
          </div>
        ))}
      </div>

      <div className="tbl-wrap">
        <div className="tbl-toolbar">
          <span className="tbl-toolbar__title">Anomaly Log</span>
          <select className="field__input" style={{ width: 140 }} value={sevF} onChange={e => setSevF(e.target.value)}>
            <option value="">All Severities</option>
            {SEVERITIES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select className="field__input" style={{ width: 200 }} value={typeF} onChange={e => setTypeF(e.target.value)}>
            <option value="">All Types</option>
            {Object.keys(TYPE_LABELS).map(v => <option key={v} value={v}>{TYPE_LABELS[v]}</option>)}
          </select>
          <select
            className="field__input"
            style={{ width: 130 }}
            value={statusF}
            onChange={e => setStatusF(e.target.value as 'all' | 'open' | 'resolved')}
          >
            <option value="all">All</option>
            <option value="open">Open</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Source Document</th><th>Khasra No.</th><th>Anomaly Type</th><th>Severity</th>
                <th>Description</th><th>Confidence</th><th>Detected</th><th>Status</th><th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(a => {
                const confColor = confidenceColor(a.confidence_pct);
                return (
                  <tr key={a.id} style={{ opacity: a.resolved ? 0.6 : 1 }}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }} className="truncate">
                        <FileText size={12} color="var(--text-tertiary)"/>
                        <span className="truncate" style={{ maxWidth: 160 }}>{a.document_name}</span>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                        {a.document_type.replace(/_/g, ' ').toLowerCase()}
                        {a.district ? ` · ${a.district}` : ''}
                      </div>
                    </td>
                    <td>
                      {a.land_record_id ? (
                        <Link
                          to={`/land-records/${a.land_record_id}`}
                          style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-navy-700)' }}
                        >
                          {a.khasra_number ?? '—'}
                        </Link>
                      ) : (
                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>unlinked</span>
                      )}
                    </td>
                    <td>
                      <span className="badge" style={{ background: 'var(--color-slate-100)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)' }}>
                        {TYPE_LABELS[a.anomaly_type] ?? a.anomaly_type.replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td><span className={`badge badge--${a.severity}`}>{a.severity}</span></td>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', maxWidth: 260 }}>
                      {a.description}
                      {a.field_name && (
                        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
                          field: {a.field_name}
                        </div>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div style={{ width: 50, height: 4, background: 'var(--color-slate-100)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${a.confidence_pct}%`, background: confColor, borderRadius: 2 }}/>
                        </div>
                        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: confColor }}>{a.confidence_pct}%</span>
                      </div>
                    </td>
                    <td style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>{formatRelative(a.created_at)}</td>
                    <td>
                      {a.resolved
                        ? <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--color-success-600)', fontWeight: 600 }}><CheckCircle size={12}/>Resolved</span>
                        : <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 'var(--text-xs)', color: 'var(--color-warning-600)' }}><AlertTriangle size={12}/>Open</span>
                      }
                    </td>
                    <td>
                      {!a.resolved && (
                        <button
                          className="btn btn--ghost btn--xs"
                          onClick={() => { void resolve(a.id); }}
                          disabled={resolving === a.id}
                        >
                          {resolving === a.id ? 'Resolving…' : 'Resolve'}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}

              {loading && anomalies.length === 0 && (
                <tr><td colSpan={9} style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-tertiary)' }}>Loading anomalies…</td></tr>
              )}

              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={9}>
                    <div className="empty" style={{ padding: 'var(--space-6)' }}>
                      <div className="empty__icon">✅</div>
                      <div className="empty__title">No anomalies to show</div>
                      <div className="empty__desc">
                        {anomalies.length === 0
                          ? 'Nothing has been flagged yet. Anomalies appear here as soon as an uploaded document finishes processing.'
                          : 'No anomaly matches the current filters.'}
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
