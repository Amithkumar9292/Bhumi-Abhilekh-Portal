/**
 * Intake Review Page — shown after OCR pipeline completes.
 *
 * Displays:
 *  - Document metadata (filename, type, size)
 *  - Pipeline metrics (confidence, language, quality)
 *  - All extracted fields in a table with:
 *    - Extracted value (or "Not detected — requires verification")
 *    - Confidence score with color-coded bar
 *    - Validation status badge
 *    - Source page
 *    - Editable input for correction
 *  - Anomalies panel
 *  - Confirm / reject buttons
 *
 * On confirm, calls POST /intake/confirm/{jobId}/submit with corrections.
 * Redirects to /land-records/{land_record_id} on success.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle, XCircle, AlertTriangle, Info, Loader2,
  RefreshCw, FileText, ChevronDown, ChevronUp, ArrowLeft, ArrowRight,
} from 'lucide-react';
import {
  intakeApi,
  describeIntakeError,
  type IntakeReviewResponse,
  type ExtractedField,
} from '../api/intake';
import { TERMINAL_JOB_STATES } from '../types/document';
import { POLL_TIMEOUT_MS } from '../api/client';
import { formatFileSize, formatRelative } from '../utils/formatters';

// ── Confidence helpers ────────────────────────────────────────────────────────
function confColor(pct: number): string {
  if (pct >= 80) return 'var(--color-success-600)';
  if (pct >= 60) return 'var(--color-warning-600)';
  return 'var(--color-error-600)';
}
function confBg(pct: number): string {
  if (pct >= 80) return 'var(--color-success-50)';
  if (pct >= 60) return 'var(--color-warning-50)';
  return 'var(--color-error-50)';
}
function confLabel(pct: number): string {
  if (pct >= 80) return 'High';
  if (pct >= 60) return 'Medium';
  return 'Low';
}

function ConfidenceBar({ pct }: { pct: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, background: 'var(--color-slate-100)', borderRadius: 999, height: 6, overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${pct}%`,
          background: confColor(pct),
          borderRadius: 999,
          transition: 'width 0.4s ease',
        }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color: confColor(pct), minWidth: 30, textAlign: 'right' }}>
        {pct}%
      </span>
    </div>
  );
}

function ValidationBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string }> = {
    AUTO_VALID:      { label: 'Auto Valid',    color: 'var(--color-success-700)', bg: 'var(--color-success-50)' },
    AUTO_INVALID:    { label: 'Auto Invalid',  color: 'var(--color-error-700)',   bg: 'var(--color-error-50)' },
    NOT_VALIDATED:   { label: 'Not Validated', color: 'var(--color-warning-700)', bg: 'var(--color-warning-50)' },
    HUMAN_VERIFIED:  { label: 'Verified',      color: 'var(--color-success-700)', bg: 'var(--color-success-50)' },
    HUMAN_REJECTED:  { label: 'Rejected',      color: 'var(--color-error-700)',   bg: 'var(--color-error-50)' },
  };
  const s = map[status] ?? { label: status, color: 'var(--text-secondary)', bg: 'var(--color-slate-50)' };
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: 99,
      fontSize: 10,
      fontWeight: 700,
      color: s.color,
      background: s.bg,
      whiteSpace: 'nowrap',
    }}>
      {s.label}
    </span>
  );
}

// ── Field row ─────────────────────────────────────────────────────────────────
interface FieldRowProps {
  field: ExtractedField;
  correction: string;
  onCorrect: (value: string) => void;
}

function FieldRow({ field, correction, onCorrect }: FieldRowProps) {
  const [editing, setEditing] = useState(false);
  const displayVal = correction !== '' ? correction : (field.normalized_value ?? '');
  const isModified = correction !== '' && correction !== (field.normalized_value ?? '');
  const isMissing = !field.normalized_value && !correction;

  return (
    <tr style={{
      background: isMissing
        ? 'rgba(239,68,68,0.03)'
        : isModified
        ? 'rgba(16,185,129,0.03)'
        : undefined,
    }}>
      <td style={{ padding: '10px 12px' }}>
        <div style={{ fontWeight: 600, fontSize: 'var(--text-xs)', color: 'var(--text-primary)' }}>
          {field.field_display ?? field.field_name}
        </div>
        {field.source_page && (
          <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
            Page {field.source_page}
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', minWidth: 220 }}>
        {editing ? (
          <input
            className="field__input"
            style={{ height: 28, fontSize: 'var(--text-xs)', padding: '0 8px' }}
            value={displayVal}
            onChange={e => onCorrect(e.target.value)}
            onBlur={() => setEditing(false)}
            autoFocus
          />
        ) : (
          <div
            style={{ cursor: 'pointer', minHeight: 28, display: 'flex', alignItems: 'center' }}
            onClick={() => setEditing(true)}
            title="Click to edit"
          >
            {isMissing ? (
              <span style={{ color: 'var(--color-error-500)', fontSize: 'var(--text-xs)', fontStyle: 'italic' }}>
                Not detected — click to enter
              </span>
            ) : (
              <span style={{
                fontSize: 'var(--text-xs)',
                fontWeight: isModified ? 600 : 500,
                color: isModified ? 'var(--color-success-700)' : 'var(--text-primary)',
                fontFamily: ['khasra_number', 'survey_number', 'khata_number', 'mutation_number'].includes(field.field_name)
                  ? 'var(--font-mono)' : undefined,
              }}>
                {displayVal}
                {isModified && <span style={{ fontSize: 9, color: 'var(--color-success-600)', marginLeft: 4 }}>✎ edited</span>}
              </span>
            )}
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', minWidth: 130 }}>
        {field.normalized_value ? (
          <ConfidenceBar pct={field.confidence_pct} />
        ) : (
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>—</span>
        )}
      </td>

      <td style={{ padding: '10px 12px' }}>
        <ValidationBadge status={isModified ? 'HUMAN_VERIFIED' : field.validation_status} />
        {field.needs_review && !isModified && (
          <div style={{ fontSize: 9, color: 'var(--color-warning-600)', marginTop: 2, fontWeight: 600 }}>
            ⚠ Needs review
          </div>
        )}
      </td>

      <td style={{ padding: '10px 12px', textAlign: 'center' }}>
        {field.raw_value && (
          <span style={{ fontSize: 10, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
            {field.raw_value.slice(0, 20)}{field.raw_value.length > 20 ? '…' : ''}
          </span>
        )}
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export function IntakeReviewPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [review, setReview] = useState<IntakeReviewResponse | null>(null);
  const [fetchError, setFetchError] = useState('');
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [showAnomalies, setShowAnomalies] = useState(true);
  const [showRaw, setShowRaw] = useState(false);

  const load = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    setFetchError('');
    try {
      const data = await intakeApi.getReview(jobId);
      setReview(data);
    } catch (err) {
      setFetchError(describeIntakeError(err));
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => { void load(); }, [load]);

  // ── Auto-reload while the pipeline is still working ───────────────────────
  // `status` is the coarse lowercase JobState, so it must be compared against
  // TERMINAL_JOB_STATES. An uppercase literal never matches, which pinned this
  // page on "Still Processing" even after the job had finished.
  useEffect(() => {
    if (!review) return;
    if (TERMINAL_JOB_STATES.has(review.status)) return;
    const t = setTimeout(() => void load(), POLL_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [review, load]);

  // ── Confirm ────────────────────────────────────────────────────────────────
  async function handleConfirm() {
    if (!jobId) return;
    setSaving(true);
    setSaveError('');
    try {
      const res = await intakeApi.confirm(jobId, { corrections, notes });
      navigate(`/land-records/${res.land_record_id}`, {
        state: { fromIntake: true, khasraNumber: res.khasra_number },
      });
    } catch (err) {
      setSaveError(describeIntakeError(err));
      setSaving(false);
    }
  }

  // ── Loading state ──────────────────────────────────────────────────────────
  if (loading && !review) {
    return (
      <div className="anim-fade-up" style={{ maxWidth: 760, margin: '0 auto', textAlign: 'center', padding: 'var(--space-16)' }}>
        <Loader2 size={32} className="spin" style={{ margin: '0 auto var(--space-4)', display: 'block', color: 'var(--color-navy-600)' }} />
        <div style={{ color: 'var(--text-secondary)' }}>Loading review data…</div>
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="anim-fade-up" style={{ maxWidth: 600, margin: 'var(--space-16) auto' }}>
        <div className="alert alert--error">
          <AlertTriangle size={16} />
          <span>{fetchError}</span>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-4)' }}>
          <button className="btn btn--secondary btn--md" onClick={() => navigate('/intake')}>
            <ArrowLeft size={14} /> Back to Intake
          </button>
          <button className="btn btn--primary btn--md" onClick={() => void load()}>
            <RefreshCw size={14} /> Retry
          </button>
        </div>
      </div>
    );
  }

  if (!review) return null;

  // Still processing. `verification_required` is terminal: the automated work is
  // finished and the fields below are what the human is being asked to confirm,
  // so it must render the review table rather than a spinner.
  if (!TERMINAL_JOB_STATES.has(review.status)) {
    return (
      <div className="anim-fade-up" style={{ maxWidth: 520, margin: '0 auto', textAlign: 'center', padding: 'var(--space-16) var(--space-4)' }}>
        <Loader2 size={36} className="spin" style={{ margin: '0 auto var(--space-5)', display: 'block', color: 'var(--color-navy-600)' }} />
        <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
          Still Processing
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-4)' }}>
          {review.current_stage?.replace(/_/g, ' ')} · {review.progress_pct}%
        </p>
        <div style={{ background: 'var(--color-slate-100)', borderRadius: 999, height: 8, overflow: 'hidden', margin: '0 auto var(--space-4)', maxWidth: 320 }}>
          <div style={{
            height: '100%',
            width: `${Math.max(5, review.progress_pct)}%`,
            background: 'linear-gradient(90deg, var(--color-navy-700), var(--color-navy-400))',
            borderRadius: 999,
            transition: 'width 0.5s ease',
          }} />
        </div>
        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
          Page will refresh automatically
        </div>
        {review.stage_message && (
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', marginTop: 'var(--space-3)' }}>
            {review.stage_message}
          </div>
        )}
      </div>
    );
  }

  // Failed
  if (review.status === 'failed') {
    return (
      <div className="anim-fade-up" style={{ maxWidth: 560, margin: 'var(--space-12) auto' }}>
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          <XCircle size={16} />
          <div>
            <strong>Pipeline Failed</strong>
            <div style={{ marginTop: 4, fontSize: 'var(--text-xs)' }}>{review.error_message ?? 'Unknown error'}</div>
          </div>
        </div>
        <button className="btn btn--secondary btn--md" onClick={() => navigate('/intake')}>
          <ArrowLeft size={14} /> Back to Intake
        </button>
      </div>
    );
  }

  const fields = review.extracted_fields;
  const reviewFields = fields.filter(f => f.needs_review);
  const highConf = fields.filter(f => f.confidence_pct >= 80).length;
  const missingFields = fields.filter(f => !f.normalized_value).length;

  return (
    <div className="anim-fade-up" style={{ maxWidth: 1100, margin: '0 auto' }}>
      {/* ── Header ────────────────────────────────────────────── */}
      <div className="page-hdr">
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)' }}>
          <button className="btn btn--ghost btn--sm" onClick={() => navigate('/intake')}>
            <ArrowLeft size={14} />
          </button>
          <div>
            <div className="page-hdr__title">Review Extracted Data</div>
            <div className="page-hdr__sub">
              {review.document.original_filename} · Verify and correct the extracted land-record fields
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn--ghost btn--sm" onClick={() => void load()} title="Refresh">
            <RefreshCw size={13} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* ── Metrics row ────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        {[
          {
            label: 'Overall Confidence',
            value: `${review.overall_confidence_pct}%`,
            sub: confLabel(review.overall_confidence_pct),
            color: confColor(review.overall_confidence_pct),
            bg: confBg(review.overall_confidence_pct),
          },
          {
            label: 'Fields Detected',
            value: `${highConf} / ${fields.length}`,
            sub: 'with high confidence',
            color: 'var(--color-navy-700)',
            bg: 'var(--color-navy-50)',
          },
          {
            label: 'Missing Fields',
            value: String(missingFields),
            sub: missingFields === 0 ? 'All fields found' : 'require manual entry',
            color: missingFields === 0 ? 'var(--color-success-600)' : 'var(--color-error-600)',
            bg: missingFields === 0 ? 'var(--color-success-50)' : 'var(--color-error-50)',
          },
          {
            label: 'Needs Review',
            value: String(reviewFields.length),
            sub: 'low confidence fields',
            color: reviewFields.length === 0 ? 'var(--color-success-600)' : 'var(--color-warning-600)',
            bg: reviewFields.length === 0 ? 'var(--color-success-50)' : 'var(--color-warning-50)',
          },
        ].map(m => (
          <div key={m.label} className="card" style={{ padding: 'var(--space-4)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{m.label}</div>
            <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 800, color: m.color, lineHeight: 1 }}>{m.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{m.sub}</div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 'var(--space-5)', alignItems: 'start' }}>
        {/* ── Extracted fields table ────────────────────────────── */}
        <div>
          <div className="card">
            <div className="card__hdr">
              <div>
                <div className="card__title">Extracted Fields</div>
                <div className="card__sub">Click any value to edit it. Red = not detected, yellow = low confidence.</div>
              </div>
              <button
                className="btn btn--ghost btn--xs"
                onClick={() => setShowRaw(v => !v)}
                style={{ fontSize: 11 }}
              >
                {showRaw ? 'Hide' : 'Show'} raw {showRaw ? <ChevronUp size={11} /> : <ChevronDown size={11} />}
              </button>
            </div>

            <div className="tbl-scroll">
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 160 }}>Field</th>
                    <th>Extracted Value</th>
                    <th style={{ width: 140 }}>Confidence</th>
                    <th style={{ width: 120 }}>Status</th>
                    {showRaw && <th style={{ width: 140 }}>Raw OCR</th>}
                  </tr>
                </thead>
                <tbody>
                  {fields.map(field => (
                    <FieldRow
                      key={field.id}
                      field={field}
                      correction={corrections[field.field_name] ?? ''}
                      onCorrect={val => setCorrections(prev => ({ ...prev, [field.field_name]: val }))}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Anomalies panel */}
          {review.anomalies.length > 0 && (
            <div className="card" style={{ marginTop: 'var(--space-4)' }}>
              <div
                className="card__hdr"
                style={{ cursor: 'pointer' }}
                onClick={() => setShowAnomalies(v => !v)}
              >
                <div>
                  <div className="card__title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlertTriangle size={14} color="var(--color-warning-600)" />
                    {review.anomalies.length} Anomaly{review.anomalies.length > 1 ? 'ies' : ''} Detected
                  </div>
                </div>
                {showAnomalies ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </div>
              {showAnomalies && (
                <div className="card__body">
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                    {review.anomalies.map(a => (
                      <div key={a.id} style={{
                        padding: 'var(--space-3)',
                        background: a.severity === 'HIGH' ? 'var(--color-error-50)' : 'var(--color-warning-50)',
                        border: `1px solid ${a.severity === 'HIGH' ? 'var(--color-error-100)' : 'var(--color-warning-100)'}`,
                        borderRadius: 'var(--radius-md)',
                        display: 'flex', gap: 'var(--space-3)', alignItems: 'flex-start',
                      }}>
                        <AlertTriangle size={14} color={a.severity === 'HIGH' ? 'var(--color-error-600)' : 'var(--color-warning-600)'} style={{ flexShrink: 0, marginTop: 2 }} />
                        <div>
                          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: a.severity === 'HIGH' ? 'var(--color-error-700)' : 'var(--color-warning-700)' }}>
                            {a.anomaly_type.replace(/_/g, ' ')} · {a.severity}
                            {a.field_name && <span style={{ fontWeight: 400, marginLeft: 6 }}>({a.field_name})</span>}
                          </div>
                          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>{a.description}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Right sidebar ─────────────────────────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', position: 'sticky', top: 'calc(var(--topbar-height, 60px) + var(--space-4))' }}>

          {/* Document info */}
          <div className="card">
            <div className="card__hdr"><div className="card__title" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <FileText size={14} /> Document
            </div></div>
            <div className="card__body">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                {[
                  ['File', review.document.original_filename],
                  ['Type', review.document.document_type.replace(/_/g, ' ')],
                  ['Size', formatFileSize(review.document.file_size_bytes)],
                  ['Language', review.detected_language ?? 'Unknown'],
                  ['Pages', String(review.page_count ?? 1)],
                  ['Quality Score', review.image_quality_score != null ? `${Math.round(review.image_quality_score * 100)}%` : '—'],
                  ['Uploaded', formatRelative(review.document.created_at)],
                ].map(([l, v]) => (
                  <div key={l} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 'var(--text-xs)' }}>
                    <span style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}>{l}</span>
                    <span style={{ fontWeight: 500, color: 'var(--text-primary)', textAlign: 'right' }} className="truncate">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Land record summary */}
          {review.land_record && (
            <div className="card">
              <div className="card__hdr">
                <div className="card__title">Land Record (Draft)</div>
                <span className="badge" style={{ background: 'var(--color-warning-50)', color: 'var(--color-warning-700)', fontSize: 10 }}>
                  {review.land_record.status}
                </span>
              </div>
              <div className="card__body">
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  {[
                    ['Khasra', review.land_record.khasra_number],
                    ['Owner', review.land_record.owner_name],
                    ['Village', review.land_record.village],
                    ['District', review.land_record.district],
                    ['State', review.land_record.state],
                    ['Area', `${review.land_record.area_hectares} ha`],
                    ['Land Use', review.land_record.land_use_type ?? '—'],
                  ].map(([l, v]) => {
                    const isDraft = ['UNKNOWN — PENDING OCR', 'DRAFT-PENDING-OCR'].includes(String(v));
                    return (
                      <div key={l} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 'var(--text-xs)' }}>
                        <span style={{ color: 'var(--text-tertiary)', flexShrink: 0 }}>{l}</span>
                        <span style={{ fontWeight: 500, color: isDraft ? 'var(--color-error-500)' : 'var(--text-primary)', textAlign: 'right', fontStyle: isDraft ? 'italic' : undefined }} className="truncate">
                          {isDraft ? 'Not extracted' : String(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Confirm / save panel. A job that is already COMPLETED has been
              saved, so there is nothing left to confirm -- offering the button
              there would invite re-confirming a finalized record. Intake
              redirects completed jobs here too, so this state is reachable. */}
          {review.status === 'completed' ? (
            <div className="card">
              <div className="card__hdr">
                <div className="card__title">Record Saved</div>
              </div>
              <div className="card__body">
                <div className="alert alert--success" style={{ marginBottom: 'var(--space-3)' }}>
                  <CheckCircle size={12} />
                  <span style={{ fontSize: 11 }}>
                    This record has been saved. The values above are what was read
                    from the document.
                  </span>
                </div>
                {review.land_record?.status && (
                  <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 'var(--space-3)' }}>
                    Record status: <strong>{review.land_record.status}</strong>
                  </p>
                )}
                {review.land_record && (
                  <button
                    className="btn btn--primary btn--md"
                    style={{ width: '100%', justifyContent: 'center' }}
                    onClick={() => navigate(`/land-records/${review.land_record!.id}`)}
                  >
                    View Land Record <ArrowRight size={14} />
                  </button>
                )}
              </div>
            </div>
          ) : (
          <div className="card">
            <div className="card__hdr"><div className="card__title">Confirm & Save</div></div>
            <div className="card__body">
              <div className="field">
                <label className="field__label">Verification Notes</label>
                <textarea
                  className="field__input"
                  rows={3}
                  placeholder="Optional notes for the record…"
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                />
              </div>

              {Object.keys(corrections).length > 0 && (
                <div className="alert alert--info" style={{ marginTop: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
                  <Info size={12} />
                  <span style={{ fontSize: 11 }}>
                    {Object.keys(corrections).length} field{Object.keys(corrections).length > 1 ? 's' : ''} manually edited
                  </span>
                </div>
              )}

              {saveError && (
                <div className="alert alert--error" style={{ marginTop: 'var(--space-3)', marginBottom: 'var(--space-3)' }}>
                  <AlertTriangle size={12} />
                  <span style={{ fontSize: 11 }}>{saveError}</span>
                </div>
              )}

              <button
                className="btn btn--success btn--md"
                style={{ width: '100%', justifyContent: 'center', marginTop: 'var(--space-3)' }}
                onClick={handleConfirm}
                disabled={saving}
              >
                {saving ? <><Loader2 size={14} className="spin" /> Saving…</> : <><CheckCircle size={14} /> Confirm & Save Record</>}
              </button>

              <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 'var(--space-2)', textAlign: 'center' }}>
                Record will be saved as UNDER_REVIEW for officer approval.
              </p>
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  );
}
