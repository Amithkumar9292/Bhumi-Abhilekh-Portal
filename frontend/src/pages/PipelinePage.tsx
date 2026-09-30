import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import {
  Upload, CheckCircle, XCircle, AlertTriangle, Activity,
  RefreshCw, User, Zap, Loader2,
} from 'lucide-react';

import {
  pipelineApi,
  type PipelineJobListItem, type PipelineJobDetail, type PipelineField,
} from '../api/pipeline';
import { describeError } from '../api/documents';
import { ACTIVE_JOB_STATES, TERMINAL_JOB_STATES, type JobState, type PipelineStage } from '../types/document';
import { formatRelative } from '../utils/formatters';

// ── Real pipeline stages ───────────────────────────────────────────────────────
// Mirrors STAGE_ORDER in app/services/pipeline_stages.py. The previous hardcoded
// list used names the backend never emits (QUALITY_ANALYSIS, OCR_RUNNING,
// DEDUP_CHECK, HUMAN_REVIEW), so the progress bar could never line up with a
// real job's current stage.
const STAGES: PipelineStage[] = [
  'QUEUED', 'FILE_VALIDATION', 'IMAGE_QUALITY', 'PREPROCESSING', 'OCR',
  'LANGUAGE_DETECTION', 'FIELD_EXTRACTION', 'CLASSIFICATION',
  'CONFIDENCE_SCORING', 'VALIDATION', 'DUPLICATE_CHECK', 'ANOMALY_CHECK',
  'VERIFICATION_REQUIRED', 'COMPLETED',
];

const STAGE_LABELS: Record<string, string> = {
  QUEUED: 'Queued',
  FILE_VALIDATION: 'File validation',
  IMAGE_QUALITY: 'Image quality',
  PREPROCESSING: 'Preprocessing',
  OCR: 'OCR',
  LANGUAGE_DETECTION: 'Language',
  FIELD_EXTRACTION: 'Extraction',
  CLASSIFICATION: 'Classification',
  CONFIDENCE_SCORING: 'Confidence',
  VALIDATION: 'Validation',
  DUPLICATE_CHECK: 'Duplicate check',
  ANOMALY_CHECK: 'Anomaly check',
  VERIFICATION_REQUIRED: 'Verification',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
};

const STATUS_CONFIG: Record<JobState, { label: string; color: string; bg: string }> = {
  queued:                 { label: 'Queued',         color: 'var(--color-slate-500)',   bg: 'var(--color-slate-50)' },
  processing:             { label: 'Processing',     color: 'var(--color-info-600)',    bg: 'var(--color-info-50)' },
  verification_required:  { label: 'Pending Review', color: 'var(--color-warning-600)', bg: 'var(--color-warning-50)' },
  completed:              { label: 'Completed',      color: 'var(--color-success-600)', bg: 'var(--color-success-50)' },
  failed:                 { label: 'Failed',         color: 'var(--color-error-600)',   bg: 'var(--color-error-50)' },
};

const SEVERITY_COLORS: Record<string, string> = {
  HIGH: 'var(--color-error-600)',
  MEDIUM: 'var(--color-warning-600)',
  LOW: 'var(--color-info-600)',
};

const FIELD_LABELS: Record<string, string> = {
  khasra_number: 'Khasra Number',
  khata_number: 'Khata Number',
  khatauni_number: 'Khatauni Number',
  survey_number: 'Survey Number',
  owner_name: 'Owner Name',
  father_name: "Father's Name",
  land_area: 'Land Area (ha)',
  area_hectares: 'Land Area (ha)',
  village: 'Village',
  tehsil: 'Tehsil',
  district: 'District',
  state: 'State',
  pin_code: 'PIN Code',
  land_classification: 'Land Classification',
  land_use_type: 'Land Use Type',
  mutation_number: 'Mutation Number',
  registration_date: 'Registration Date',
};

/** Fraction (0-1) to a percentage string, or an em-dash when unknown. */
function pct(value: number | null | undefined): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`;
}

function ConfidencePill({ value }: { value: number }) {
  const p = Math.round(value * 100);
  const color = p >= 80 ? 'var(--color-success-600)' : p >= 60 ? 'var(--color-warning-600)' : 'var(--color-error-600)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 56, height: 4, background: 'var(--color-slate-100)', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${p}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600, color }}>{p}%</span>
    </div>
  );
}

/** Pipeline stage dots, driven by the real stage names and progress percentage. */
function StageProgress({ stage, status, progress }: { stage: string | null; status: JobState; progress: number }) {
  const currentIdx = stage ? STAGES.indexOf(stage as PipelineStage) : status === 'completed' ? STAGES.length - 1 : -1;
  const failed = status === 'failed';

  return (
    <div style={{ padding: 'var(--space-4) var(--space-5)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
        {STAGES.map((s, i) => {
          const done = i < currentIdx || status === 'completed';
          const active = i === currentIdx && status === 'processing';
          const isFailure = failed && i === currentIdx;
          return (
            <div key={s} style={{ flex: 1, display: 'flex', alignItems: 'center' }} title={STAGE_LABELS[s]}>
              <div style={{
                width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                background: isFailure ? 'var(--color-error-500)' : done ? 'var(--color-success-500)' : active ? 'var(--color-navy-700)' : 'var(--color-slate-200)',
                border: active ? '2px solid var(--color-navy-300)' : 'none',
                boxShadow: active ? '0 0 0 3px rgba(0,53,128,0.15)' : 'none',
              }} />
              {i < STAGES.length - 1 && (
                <div style={{
                  flex: 1, height: 2,
                  background: done ? 'var(--color-success-200)' : 'var(--color-slate-150)',
                  margin: '0 1px',
                }} />
              )}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text-secondary)' }}>
        {stage ? (
          <>
            <span style={{ color: failed ? 'var(--color-error-600)' : 'var(--color-navy-700)', fontWeight: 700 }}>
              {STAGE_LABELS[stage] ?? stage}
            </span>
            {' · '}{progress}% complete
          </>
        ) : (
          <span style={{ color: 'var(--text-tertiary)' }}>No stage recorded</span>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export function PipelinePage() {
  const [jobs, setJobs] = useState<PipelineJobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<PipelineJobDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [filter, setFilter] = useState<JobState | 'ALL'>('ALL');
  const [fieldTab, setFieldTab] = useState<'fields' | 'anomalies'>('fields');
  const [verifyingField, setVerifyingField] = useState<string | null>(null);
  const [verifyValue, setVerifyValue] = useState('');
  const [verifyBusy, setVerifyBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [retrying, setRetrying] = useState(false);

  const loadJobs = useCallback(async () => {
    try {
      const res = await pipelineApi.listJobs({ page_size: 50 });
      setJobs(res.items);
      setError('');
      // Select the newest job the first time only, so a poll refresh does not
      // yank the operator's selection out from under them.
      setSelected(prev => prev ?? res.items[0]?.id ?? null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadJobs(); }, [loadJobs]);

  // While any job is still running, poll so live progress actually updates.
  useEffect(() => {
    if (!jobs.some(j => ACTIVE_JOB_STATES.has(j.status))) return;
    const t = setInterval(() => { void loadJobs(); }, 5000);
    return () => clearInterval(t);
  }, [jobs, loadJobs]);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let cancelled = false;
    setDetailLoading(true);
    pipelineApi.getJob(selected)
      .then(d => { if (!cancelled) { setDetail(d); setActionError(''); } })
      .catch(err => { if (!cancelled) setActionError(describeError(err)); })
      .finally(() => { if (!cancelled) setDetailLoading(false); });
    return () => { cancelled = true; };
  }, [selected]);

  const list = filter === 'ALL' ? jobs : jobs.filter(j => j.status === filter);
  const summary = {
    total: jobs.length,
    processing: jobs.filter(j => ACTIVE_JOB_STATES.has(j.status)).length,
    review: jobs.filter(j => j.status === 'verification_required').length,
    completed: jobs.filter(j => j.status === 'completed').length,
    failed: jobs.filter(j => j.status === 'failed').length,
  };

  const fields = detail?.extracted_fields ?? [];
  const reviewFields = fields.filter(f => f.needs_review && !f.verified_value);

  // The job list carries the canonical lower-case JobState, while the detail
  // payload spells the same state in upper case (PENDING_REVIEW). Resolve the
  // list state once so terminal-state checks do not silently miss.
  const detailState = (jobs.find(j => j.id === detail?.id)?.status) as JobState | undefined;

  // A job whose processing has finished can be re-run, including one waiting on
  // verification: if the extraction came back empty or plainly wrong, the fix is
  // to redo the OCR, not to hand-type every field.
  const canReprocess = detailState !== undefined && TERMINAL_JOB_STATES.has(detailState);

  /** Persist a verifier's correction, then reload so the server value shows. */
  async function submitVerify(field: PipelineField) {
    setVerifyBusy(true);
    setActionError('');
    try {
      await pipelineApi.verifyField(field.id, verifyValue.trim());
      const fresh = await pipelineApi.getJob(selected!);
      setDetail(fresh);
      await loadJobs();
      setVerifyingField(null);
      setVerifyValue('');
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setVerifyBusy(false);
    }
  }

  async function retry() {
    if (!selected) return;
    setRetrying(true);
    setActionError('');
    try {
      await pipelineApi.retryJob(selected);
      await loadJobs();
    } catch (err) {
      setActionError(describeError(err));
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Document Processing Pipeline</div>
          <div className="page-hdr__sub">Real-time OCR, field extraction and validation workflow</div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn--secondary btn--md" onClick={() => { setLoading(true); void loadJobs(); }}>
            <RefreshCw size={13} className={loading ? 'spin' : ''} /> Refresh
          </button>
          <Link to="/intake" className="btn btn--primary btn--md"><Upload size={13} /> Upload Document</Link>
        </div>
      </div>

      {error && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          <XCircle size={14} /><span>{error}</span>
        </div>
      )}

      {/* Summary KPIs — counted from the real jobs, not hardcoded. */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        {[
          { label: 'Total Jobs', value: summary.total, accent: '#3B82F6' },
          { label: 'Processing', value: summary.processing, accent: '#2563EB' },
          { label: 'Pending Review', value: summary.review, accent: '#D97706' },
          { label: 'Completed', value: summary.completed, accent: '#10B981' },
          { label: 'Failed', value: summary.failed, accent: '#EF4444' },
        ].map(k => (
          <div key={k.label} className="kpi">
            <div className="kpi__accent" style={{ background: k.accent }} />
            <div className="kpi__value">{k.value}</div>
            <div className="kpi__label">{k.label}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 'var(--space-5)', alignItems: 'start' }}>

        {/* Job Queue */}
        <div className="card" style={{ position: 'sticky', top: 'calc(var(--topbar-height) + var(--header-height) + var(--nav-height) + var(--space-4))' }}>
          <div className="card__hdr">
            <div className="card__title">Pipeline Queue</div>
            <select className="field__input" style={{ width: 130, height: 28, fontSize: 'var(--text-xs)' }}
              value={filter} onChange={e => setFilter(e.target.value as JobState | 'ALL')}>
              <option value="ALL">All Jobs</option>
              {Object.entries(STATUS_CONFIG).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>
          <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
            {loading && jobs.length === 0 && (
              <div style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--text-sm)' }}>
                <Loader2 size={16} className="spin" /> Loading jobs…
              </div>
            )}
            {!loading && list.length === 0 && (
              <div className="empty" style={{ padding: 'var(--space-6)' }}>
                <div className="empty__title">
                  {jobs.length === 0 ? 'No jobs yet' : 'No jobs match this filter'}
                </div>
              </div>
            )}
            {list.map(j => {
              const sc = STATUS_CONFIG[j.status];
              return (
                <div key={j.id} onClick={() => setSelected(j.id === selected ? null : j.id)}
                  style={{
                    padding: '12px 16px', borderBottom: '1px solid var(--color-slate-75)',
                    cursor: 'pointer',
                    background: j.id === selected ? 'var(--color-navy-50)' : 'white',
                    borderLeft: `3px solid ${j.id === selected ? 'var(--color-navy-700)' : 'transparent'}`,
                  }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, gap: 8 }}>
                    <span style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-navy-700)' }}>
                      {j.khasra_number ?? '—'}
                    </span>
                    <span style={{ fontSize: 10, fontWeight: 600, color: sc.color, background: sc.bg, padding: '2px 6px', borderRadius: 'var(--radius-full)', whiteSpace: 'nowrap' }}>
                      {sc.label}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 5 }} className="truncate">
                    {j.document_name ?? 'Unknown document'}
                  </div>
                  {ACTIVE_JOB_STATES.has(j.status) && (
                    <div className="progress" style={{ marginBottom: 4 }}>
                      <div className="progress__fill" style={{ width: `${j.progress_pct}%`, background: 'var(--color-navy-700)' }} />
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 8, fontSize: 10, color: 'var(--text-tertiary)' }}>
                    {j.overall_confidence != null && (
                      <span>Conf: <strong style={{ color: 'var(--text-secondary)' }}>{pct(j.overall_confidence)}</strong></span>
                    )}
                    {j.needs_human_review && <span style={{ color: 'var(--color-warning-600)' }}>⚠ Review needed</span>}
                    {j.is_duplicate && <span style={{ color: 'var(--color-error-600)' }}>⚠ Duplicate</span>}
                    {j.status === 'failed' && j.failed_stage && (
                      <span style={{ color: 'var(--color-error-600)' }}>at {STAGE_LABELS[j.failed_stage] ?? j.failed_stage}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Detail panel */}
        {selected ? (
          <div className="anim-fade-in">
            {detailLoading && !detail && (
              <div className="card" style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
                <Loader2 size={18} className="spin" /> Loading job…
              </div>
            )}

            {actionError && (
              <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
                <XCircle size={14} /><span>{actionError}</span>
              </div>
            )}

            {detail && (
              <>
                {/* Job header */}
                <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
                  <div className="card__hdr">
                    <div>
                      <div className="card__title">
                        {jobs.find(j => j.id === detail.id)?.document_name ?? 'Document'}
                      </div>
                      <div className="card__sub">
                        Job ID: <code style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>{detail.id}</code>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                      {ACTIVE_JOB_STATES.has(detail.status as JobState) && (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--color-info-600)', fontWeight: 600 }}>
                          <Activity size={13} /> Live
                        </span>
                      )}
                      <span className={`badge badge--${
                        detail.status === 'COMPLETED' ? 'VERIFIED'
                        : detail.status === 'FAILED' ? 'REJECTED'
                        : detail.status === 'PENDING_REVIEW' ? 'UNDER_REVIEW'
                        : 'PENDING'
                      }`}>
                        {STAGE_LABELS[detail.status] ?? detail.status}
                      </span>
                      {canReprocess && (
                        <button
                          className="btn btn--secondary btn--xs"
                          disabled={retrying}
                          title="Re-run OCR and field extraction for this document"
                          onClick={() => void retry()}
                        >
                          {retrying
                            ? <Loader2 size={12} className="spin" />
                            : <RefreshCw size={12} />}
                          Reprocess
                        </button>
                      )}
                    </div>
                  </div>

                  <StageProgress
                    stage={detail.current_stage}
                    status={(jobs.find(j => j.id === detail.id)?.status ?? 'processing') as JobState}
                    progress={detail.progress_pct}
                  />

                  <div style={{ display: 'flex', gap: 'var(--space-6)', padding: '0 var(--space-5) var(--space-4)', flexWrap: 'wrap' }}>
                    {[
                      ['Overall Confidence', pct(detail.overall_confidence)],
                      ['Language', detail.detected_language ?? '—'],
                      ['Pages', detail.page_count ?? '—'],
                      ['Quality Score', pct(detail.image_quality_score)],
                      ['Duplicate', detail.is_duplicate ? '⚠ Yes' : 'No'],
                      ['Anomalies', detail.anomalies.length > 0 ? `${detail.anomalies.length} found` : 'None'],
                      ['Queued', formatRelative(detail.created_at)],
                    ].map(([l, v]) => (
                      <div key={String(l)}>
                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{l}</div>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)' }}>{v}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Human review tasks */}
                {reviewFields.length > 0 && (
                  <div className="card" style={{ marginBottom: 'var(--space-4)', border: '1px solid var(--color-warning-200)' }}>
                    <div className="card__hdr" style={{ background: 'var(--color-warning-50)', borderRadius: 'var(--radius-xl) var(--radius-xl) 0 0' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <User size={14} color="var(--color-warning-600)" />
                        <div className="card__title" style={{ color: 'var(--color-warning-800)' }}>
                          Human Verification Required ({reviewFields.length} fields)
                        </div>
                      </div>
                    </div>
                    <div className="card__body">
                      {reviewFields.map(f => (
                        <div key={f.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--color-slate-75)' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                            <div style={{ flex: 1 }}>
                              <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: 3 }}>
                                {f.field_display ?? FIELD_LABELS[f.field_name] ?? f.field_name}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                                <code style={{ fontSize: 11, background: 'var(--color-slate-100)', padding: '1px 6px', borderRadius: 'var(--radius-xs)', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                                  {f.normalized_value ?? f.raw_value ?? '(not extracted)'}
                                </code>
                                <ConfidencePill value={f.confidence_score} />
                                <span className="badge badge--REJECTED" style={{ fontSize: 10 }}>Needs Review</span>
                              </div>
                            </div>
                            <button
                              className="btn btn--secondary btn--xs"
                              onClick={() => { setVerifyingField(f.id); setVerifyValue(f.normalized_value ?? f.raw_value ?? ''); }}
                            >
                              <CheckCircle size={11} /> Verify
                            </button>
                          </div>

                          {verifyingField === f.id && (
                            <div style={{ marginTop: 8, display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                              <input className="field__input" style={{ flex: 1 }} value={verifyValue}
                                onChange={e => setVerifyValue(e.target.value)}
                                placeholder="Enter correct value…" />
                              <button className="btn btn--success btn--xs" disabled={verifyBusy || !verifyValue.trim()} onClick={() => void submitVerify(f)}>
                                {verifyBusy ? <Loader2 size={11} className="spin" /> : null} Confirm
                              </button>
                              <button className="btn btn--ghost btn--xs" onClick={() => setVerifyingField(null)}>Cancel</button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Tabs: Extracted Fields / Anomalies */}
                {fields.length > 0 && (
                  <div className="card">
                    <div className="card__hdr" style={{ paddingBottom: 0, borderBottom: 'none' }}>
                      <div className="tabs" style={{ gap: 0, margin: 0 }}>
                        {([['fields', 'Extracted Fields'], ['anomalies', 'Anomalies']] as const).map(([id, label]) => (
                          <button key={id} className={`tab-btn${fieldTab === id ? ' active' : ''}`} onClick={() => setFieldTab(id)}>
                            {id === 'fields' ? <Zap size={12} /> : <AlertTriangle size={12} />} {label}
                            <span className="tab-btn__count">{id === 'fields' ? fields.length : detail.anomalies.length}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {fieldTab === 'fields' && (
                      <div className="tbl-scroll anim-fade-in">
                        <table className="tbl">
                          <thead>
                            <tr>
                              <th>Field</th><th>Extracted Value</th><th>Confidence</th>
                              <th>Validation</th><th>Page</th><th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {fields.map(f => {
                              const value = f.verified_value ?? f.normalized_value ?? f.raw_value;
                              const verified = Boolean(f.verified_value);
                              return (
                                <tr key={f.id} style={{ opacity: value ? 1 : 0.55 }}>
                                  <td style={{ fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                    {f.field_display ?? FIELD_LABELS[f.field_name] ?? f.field_name}
                                  </td>
                                  <td>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                      {value
                                        ? <code style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-primary)' }}>{value}</code>
                                        : <span style={{ fontSize: 11, color: 'var(--text-tertiary)', fontStyle: 'italic' }}>Not extracted</span>}
                                      {verified && (
                                        <span className="badge badge--VERIFIED" style={{ fontSize: 9 }}>VERIFIED</span>
                                      )}
                                    </div>
                                    {f.validation_message && (
                                      <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{f.validation_message}</div>
                                    )}
                                  </td>
                                  <td><ConfidencePill value={f.confidence_score} /></td>
                                  <td>
                                    <span style={{
                                      fontSize: 10, fontWeight: 600,
                                      color: verified || f.validation_status === 'AUTO_VALID' || f.validation_status === 'HUMAN_VERIFIED'
                                        ? 'var(--color-success-600)' : 'var(--color-error-600)',
                                    }}>
                                      {verified ? 'HUMAN_VERIFIED' : f.validation_status}
                                    </span>
                                  </td>
                                  <td style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{f.source_page ?? '—'}</td>
                                  <td>
                                    {f.needs_review && !verified && (
                                      <span className="badge badge--UNDER_REVIEW" style={{ fontSize: 9 }}>Review</span>
                                    )}
                                    {verified && <CheckCircle size={12} color="var(--color-success-500)" />}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {fieldTab === 'anomalies' && (
                      <div className="anim-fade-in">
                        {detail.anomalies.length === 0 ? (
                          <div className="empty" style={{ padding: 'var(--space-8)' }}>
                            <div className="empty__icon">✅</div>
                            <div className="empty__title">No anomalies detected</div>
                          </div>
                        ) : detail.anomalies.map(a => (
                          <div key={a.id} style={{ display: 'flex', gap: 12, padding: '12px 16px', borderBottom: '1px solid var(--color-slate-75)' }}>
                            <div style={{ width: 8, height: 8, borderRadius: 2, background: SEVERITY_COLORS[a.severity] ?? 'gray', flexShrink: 0, marginTop: 5 }} />
                            <div style={{ flex: 1 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                <code style={{ fontSize: 10, background: 'var(--color-slate-100)', padding: '1px 6px', borderRadius: 'var(--radius-xs)', fontFamily: 'var(--font-mono)', color: 'var(--color-navy-800)' }}>{a.anomaly_type}</code>
                                <span className={`badge badge--${a.severity}`}>{a.severity}</span>
                                {a.field_name && <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>→ {a.field_name}</span>}
                              </div>
                              <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{a.description}</div>
                            </div>
                            <div style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                              {pct(a.confidence)} conf
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {fields.length === 0 && detail.status !== 'failed' && !ACTIVE_JOB_STATES.has((jobs.find(j => j.id === detail.id)?.status ?? 'processing') as JobState) && (
                  <div className="card">
                    <div className="empty" style={{ padding: 'var(--space-8)' }}>
                      <div className="empty__icon">📄</div>
                      <div className="empty__title">No fields were extracted</div>
                      <div className="empty__desc">
                        The pipeline finished without producing any extracted fields. Check the job stage and error details above.
                      </div>
                    </div>
                  </div>
                )}

                {detail.status === 'FAILED' && (
                  <div className="alert alert--error" style={{ marginTop: 'var(--space-4)' }}>
                    <XCircle size={14} />
                    <div style={{ flex: 1 }}>
                      <strong>Pipeline Failed</strong>
                      {detail.current_stage && <> at {STAGE_LABELS[detail.current_stage] ?? detail.current_stage}</>}
                      {' — '}
                      {detail.error_message ?? 'No error message was recorded.'}
                      <div style={{ marginTop: 6 }}>
                        <button className="btn btn--danger btn--sm" disabled={retrying} onClick={() => void retry()}>
                          {retrying ? <Loader2 size={12} className="spin" /> : <RefreshCw size={12} />} Retry Pipeline
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="empty" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-xl)' }}>
            <div className="empty__icon">⚙️</div>
            <div className="empty__title">Select a job to inspect</div>
            <div className="empty__desc">Click any pipeline job from the queue to view its full extraction results, anomalies and verification tasks.</div>
          </div>
        )}
      </div>
    </div>
  );
}
