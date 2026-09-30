/**
 * Document Intake Page — Completely redesigned.
 *
 * New workflow:
 *  1. User drops/selects a file (PDF, JPG, JPEG, PNG, TIFF)
 *  2. User optionally enters a Khasra/Survey number hint
 *  3. On submit: file is uploaded → backend auto-creates a draft land record
 *  4. OCR pipeline runs in background (real-time progress shown)
 *  5. On completion: redirect to /intake/review/:jobId for extraction review
 *
 * The Khasra number is NEVER required — it's just a lookup hint.
 * If a match is found, the document is linked to the existing record.
 * If no match, a new DRAFT record is created from OCR results.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Upload, FileText, X, CheckCircle, AlertTriangle,
  Loader2, Info, ArrowRight, Search,
} from 'lucide-react';
import { intakeApi, describeIntakeError, type IntakeUploadResponse } from '../api/intake';
import {
  DOCUMENT_TYPES,
  TERMINAL_JOB_STATES,
  type DocumentType,
  type JobState,
  type PipelineStage,
} from '../types/document';
import { formatFileSize } from '../utils/formatters';

const MAX_BYTES = 20 * 1024 * 1024;
const ACCEPT = '.pdf,.jpg,.jpeg,.png,.tiff,.tif';

/** Delay between status polls. OCR is slow, so there is no reason to be greedy. */
const POLL_INTERVAL_MS = 2000;
/** ~4 minutes of polling before telling the user to check the Documents page. */
const MAX_POLL_ATTEMPTS = 120;

/** Stage → label, keyed by the canonical stage the backend reports. */
const STAGE_LABELS: Record<PipelineStage, string> = {
  QUEUED: 'Queued for processing…',
  FILE_VALIDATION: 'Validating file…',
  IMAGE_QUALITY: 'Analysing image quality…',
  PREPROCESSING: 'Preprocessing the scan…',
  OCR: 'Running OCR — reading the document…',
  LANGUAGE_DETECTION: 'Detecting language…',
  FIELD_EXTRACTION: 'Extracting land-record fields…',
  CLASSIFICATION: 'Classifying the document…',
  CONFIDENCE_SCORING: 'Scoring extraction confidence…',
  VALIDATION: 'Validating extracted values…',
  DUPLICATE_CHECK: 'Checking for duplicates…',
  ANOMALY_CHECK: 'Running anomaly detection…',
  VERIFICATION_REQUIRED: 'Routing to review…',
  COMPLETED: 'Processing complete.',
  FAILED: 'Processing failed.',
};

type UploadPhase =
  | 'idle'          // waiting for file selection
  | 'ready'         // file selected, not submitted
  | 'uploading'     // POST in flight
  | 'processing'    // pipeline running (polling)
  | 'done'          // pipeline finished → show Go to Review button
  | 'error';        // unrecoverable error

interface SelectedFile {
  file: File;
  name: string;
  size: number;
  type: string;
  previewUrl?: string;
}

export function DocumentIntakePage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [phase, setPhase] = useState<UploadPhase>('idle');
  const [selected, setSelected] = useState<SelectedFile | null>(null);
  const [dragging, setDragging] = useState(false);

  // Form fields
  const [docType, setDocType] = useState<DocumentType | ''>('');
  const [khasraHint, setKhasraHint] = useState('');
  const [remarks, setRemarks] = useState('');

  // Upload / pipeline state
  const [uploadResult, setUploadResult] = useState<IntakeUploadResponse | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<JobState>('queued');
  const [pipelineStage, setPipelineStage] = useState<PipelineStage>('QUEUED');
  const [pipelineProgress, setPipelineProgress] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  /** Stage the job failed in, so the error can name it instead of guessing. */
  const [failedStage, setFailedStage] = useState<string | null>(null);

  // Size / type error
  const [fileError, setFileError] = useState('');

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
      if (selected?.previewUrl) URL.revokeObjectURL(selected.previewUrl);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── File selection ─────────────────────────────────────────────────────────
  function selectFile(file: File) {
    setFileError('');
    setErrorMsg('');

    if (file.size > MAX_BYTES) {
      setFileError(`File too large (${formatFileSize(file.size)}). Maximum: 20 MB.`);
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
    const allowedExts = ['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif'];
    if (!allowedExts.includes(ext)) {
      setFileError(`"${ext}" files are not supported. Please use PDF, JPG, PNG or TIFF.`);
      return;
    }

    let previewUrl: string | undefined;
    if (file.type.startsWith('image/')) {
      previewUrl = URL.createObjectURL(file);
    }

    setSelected({ file, name: file.name, size: file.size, type: file.type, previewUrl });
    setPhase('ready');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) selectFile(f);
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) selectFile(f);
  }

  function clearFile() {
    if (selected?.previewUrl) URL.revokeObjectURL(selected.previewUrl);
    setSelected(null);
    setPhase('idle');
    setFileError('');
    setErrorMsg('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  // ── Pipeline polling ───────────────────────────────────────────────────────
  // A recursive setTimeout (not setInterval) so a slow or failed request cannot
  // stack up overlapping calls, and so polling stops the moment the job reaches
  // a terminal state.
  const poll = useCallback((jobId: string, attempt = 0) => {
    pollRef.current = setTimeout(async () => {
      try {
        const st = await intakeApi.pollStatus(jobId);
        setPipelineStatus(st.status);
        setPipelineStage(st.stage as PipelineStage);
        setPipelineProgress(st.progress ?? 0);

        if (st.status === 'failed') {
          setFailedStage(st.failed_stage ?? null);
          setPhase('error');
          setErrorMsg(
            st.error_message ?? 'Processing failed. Please upload a clearer scan.',
          );
          return;
        }

        if (st.status === 'verification_required' || st.status === 'completed') {
          // Automated work is done. The operator uploaded this document to see
          // what was read out of it, so take them straight to the review screen
          // instead of parking them on a summary they have to click through.
          // A completed job has nothing left to confirm, but the extracted
          // fields are still what they asked for, so it lands there too.
          if (pollRef.current) clearTimeout(pollRef.current);
          setPhase('done');
          navigate(`/intake/review/${jobId}`);
          return;
        }

        if (attempt < MAX_POLL_ATTEMPTS) {
          poll(jobId, attempt + 1);
        } else {
          // Still running after the budget. The job is not lost -- it keeps
          // going in the worker -- and the review screen already handles a
          // job that has not finished (it shows live progress), so send the
          // operator there rather than to a dead end.
          setPhase('done');
          navigate(`/intake/review/${jobId}`);
        }
      } catch {
        // Transient failure (network blip or one slow poll): keep polling.
        if (attempt < MAX_POLL_ATTEMPTS) poll(jobId, attempt + 1);
      }
    }, POLL_INTERVAL_MS);
  }, [navigate]);

  // ── Submit ─────────────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !docType) return;

    setErrorMsg('');
    setPhase('uploading');

    try {
      const res = await intakeApi.upload(
        selected.file,
        docType as DocumentType,
        khasraHint || undefined,
        remarks || undefined,
      );
      setUploadResult(res);
      setPhase('processing');
      setPipelineStatus('queued');
      setPipelineStage('QUEUED');
      setPipelineProgress(res.progress ?? 0);
      setFailedStage(null);
      poll(res.job_id);
    } catch (err) {
      setPhase('error');
      setErrorMsg(describeIntakeError(err));
    }
  }

  // ── STAGE: Done — go to review ────────────────────────────────────────────
  if (phase === 'done' && uploadResult) {
    const needsReview = pipelineStatus === 'verification_required';
    return (
      <div className="anim-fade-up" style={{ maxWidth: 620, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', padding: 'var(--space-12) var(--space-4)' }}>
          <div style={{
            width: 72, height: 72,
            background: needsReview ? 'var(--color-warning-50)' : 'var(--color-success-50)',
            border: `2px solid ${needsReview ? 'var(--color-warning-200)' : 'var(--color-success-200)'}`,
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto var(--space-6)',
          }}>
            {needsReview
              ? <AlertTriangle size={32} color="var(--color-warning-600)" />
              : <CheckCircle size={32} color="var(--color-success-600)" />}
          </div>
          <h2 style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
            {needsReview ? 'Verification Required' : 'Processing Complete'}
          </h2>
          <p style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-6)', fontSize: 'var(--text-sm)' }}>
            {needsReview
              ? 'OCR and field extraction finished. Some fields have low confidence and need your confirmation before the record is finalized.'
              : 'OCR and field extraction finished.'}
            {uploadResult.new_record_created
              ? ' A new draft land record has been created from the extracted data.'
              : ' Document linked to the existing land record.'}
          </p>

          {/* Timed out while still processing: the job is not lost. */}
          {errorMsg && (
            <div className="alert alert--info" style={{ textAlign: 'left', marginBottom: 'var(--space-6)' }}>
              {errorMsg}
            </div>
          )}

          <div className="card" style={{ textAlign: 'left', marginBottom: 'var(--space-6)' }}>
            <div className="card__body">
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                {[
                  ['File', selected?.name ?? '—'],
                  ['Document Type', docType],
                  ['Khasra Hint', khasraHint || '(not provided — OCR will extract)'],
                  ['Record', uploadResult.new_record_created ? '✨ New draft created' : '🔗 Linked to existing'],
                ].map(([l, v]) => (
                  <div key={l}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 2 }}>{l}</div>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{String(v)}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--space-3)', justifyContent: 'center' }}>
            <button
              className="btn btn--secondary btn--md"
              onClick={() => {
                if (pollRef.current) clearTimeout(pollRef.current);
                setPhase('idle');
                setSelected(null);
                setDocType('');
                setKhasraHint('');
                setRemarks('');
                setUploadResult(null);
                setPipelineStatus('queued');
                setPipelineStage('QUEUED');
                setPipelineProgress(0);
                setFailedStage(null);
                setErrorMsg('');
              }}
            >
              Upload Another
            </button>
            <button
              className="btn btn--primary btn--lg"
              onClick={() => navigate(`/intake/review/${uploadResult.job_id}`)}
            >
              Review Extracted Data <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── STAGE: Uploading / Processing ─────────────────────────────────────────
  if (phase === 'uploading' || phase === 'processing') {
    // Prefer the backend's canonical stage so new stages appear automatically.
    const stageLabel = phase === 'uploading'
      ? 'Uploading file…'
      : STAGE_LABELS[pipelineStage] ?? 'Processing…';

    return (
      <div className="anim-fade-up" style={{ maxWidth: 520, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', padding: 'var(--space-16) var(--space-4)' }}>
          <div style={{
            width: 72, height: 72,
            background: 'var(--color-navy-50)',
            border: '2px solid var(--color-navy-100)',
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto var(--space-6)',
          }}>
            <Loader2 size={32} color="var(--color-navy-700)" className="spin" />
          </div>
          <h2 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, marginBottom: 'var(--space-2)' }}>
            {stageLabel}
          </h2>
          <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', marginBottom: 'var(--space-6)' }}>
            {selected?.name} · {formatFileSize(selected?.size ?? 0)}
          </p>

          {/* Progress bar */}
          <div style={{ background: 'var(--color-slate-100)', borderRadius: 999, height: 8, overflow: 'hidden', marginBottom: 'var(--space-3)' }}>
            <div style={{
              height: '100%',
              width: `${phase === 'uploading' ? 10 : Math.max(5, pipelineProgress)}%`,
              background: 'linear-gradient(90deg, var(--color-navy-700), var(--color-navy-400))',
              borderRadius: 999,
              transition: 'width 0.5s ease',
            }} />
          </div>
          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            {phase === 'processing' ? `${pipelineProgress}% complete` : 'Uploading…'}
          </div>

          <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
            {phase === 'processing' ? 'Stage' : ''} {pipelineStage}
          </div>

          {uploadResult && (
            <div style={{ marginTop: 'var(--space-2)', fontSize: 'var(--text-xs)', color: 'var(--text-tertiary)' }}>
              {uploadResult.new_record_created
                ? '✨ New draft land record created — OCR is extracting fields'
                : '🔗 Linked to existing land record'}
            </div>
          )}

          {uploadResult?.queue_warning && (
            <div className="alert alert--warning" style={{ marginTop: 'var(--space-4)', textAlign: 'left' }}>
              {uploadResult.queue_warning}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── STAGE: Error ───────────────────────────────────────────────────────────
  // (shown inline below the form so user can retry)

  // ── STAGE: Idle / Ready (main form) ──────────────────────────────────────
  const canSubmit = Boolean(selected) && Boolean(docType) && phase === 'ready';

  return (
    <div className="anim-fade-up" style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Document Intake</div>
          <div className="page-hdr__sub">
            Upload any land-record document — a new land record will be automatically created from OCR extraction
          </div>
        </div>
      </div>

      {/* Info banner */}
      <div className="alert alert--info" style={{ marginBottom: 'var(--space-5)' }}>
        <Info size={14} style={{ flexShrink: 0 }} />
        <span>
          <strong>No existing record required.</strong>{' '}
          Upload any supported document. The Khasra/Survey number is optional — OCR will attempt to extract it automatically.
          If the number matches an existing record, the document is linked; otherwise a new draft record is created.
        </span>
      </div>

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-6)', alignItems: 'start' }}>

          {/* ── Left: Drop zone ──────────────────────────────────── */}
          <div className="card">
            <div className="card__hdr"><div className="card__title">Document File</div></div>
            <div className="card__body">
              {!selected ? (
                <label
                  className={`dropzone${dragging ? ' dropzone--active' : ''}`}
                  onDragOver={e => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  style={{ cursor: 'pointer', minHeight: 200 }}
                >
                  <input
                    type="file"
                    accept={ACCEPT}
                    style={{ display: 'none' }}
                    ref={fileInputRef}
                    onChange={handleFileChange}
                  />
                  <div className="dropzone__icon">📄</div>
                  <div className="dropzone__title">Drop your file here</div>
                  <div className="dropzone__sub">PDF, JPG, JPEG, PNG, TIFF · Max 20 MB</div>
                  <div style={{ marginTop: 'var(--space-3)' }}>
                    <span className="btn btn--secondary btn--sm">Browse Files</span>
                  </div>
                </label>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                  {/* File preview card */}
                  <div style={{
                    display: 'flex', alignItems: 'center', gap: 'var(--space-3)',
                    padding: 'var(--space-3)',
                    background: 'var(--color-success-50)',
                    border: '1px solid var(--color-success-200)',
                    borderRadius: 'var(--radius-lg)',
                  }}>
                    {selected.previewUrl ? (
                      <img
                        src={selected.previewUrl}
                        alt="Preview"
                        style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 4, flexShrink: 0 }}
                      />
                    ) : (
                      <div style={{
                        width: 48, height: 56,
                        background: 'var(--color-error-100)',
                        border: '1px solid var(--color-error-200)',
                        borderRadius: 4,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 10, fontWeight: 700, color: 'var(--color-error-700)',
                        flexShrink: 0,
                      }}>
                        {selected.name.split('.').pop()?.toUpperCase()}
                      </div>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }} className="truncate">{selected.name}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                        {formatFileSize(selected.size)} · {selected.type || 'unknown type'}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 4, fontSize: 11, color: 'var(--color-success-700)', fontWeight: 600 }}>
                        <CheckCircle size={11} /> Ready to upload
                      </div>
                    </div>
                    <button type="button" className="btn btn--ghost btn--xs" onClick={clearFile} title="Remove file">
                      <X size={14} />
                    </button>
                  </div>

                  {/* Re-select */}
                  <label style={{ cursor: 'pointer' }}>
                    <input type="file" accept={ACCEPT} style={{ display: 'none' }} onChange={handleFileChange} />
                    <span className="btn btn--ghost btn--sm" style={{ width: '100%', justifyContent: 'center' }}>
                      <Upload size={12} /> Replace file
                    </span>
                  </label>
                </div>
              )}

              {fileError && (
                <div className="alert alert--error" style={{ marginTop: 'var(--space-3)' }}>
                  <AlertTriangle size={13} />
                  <span>{fileError}</span>
                </div>
              )}
            </div>
          </div>

          {/* ── Right: Metadata ───────────────────────────────────── */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <div className="card">
              <div className="card__hdr"><div className="card__title">Document Details</div></div>
              <div className="card__body">

                <div className="field">
                  <label className="field__label field__label--req">Document Type</label>
                  <select
                    className="field__input field__input--lg"
                    value={docType}
                    onChange={e => setDocType(e.target.value as DocumentType)}
                    required
                  >
                    <option value="">Select document type…</option>
                    {DOCUMENT_TYPES.map(({ value, label }) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>

                <div className="field" style={{ marginTop: 'var(--space-4)' }}>
                  <label className="field__label">
                    Khasra / Survey Number
                    <span style={{ fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: 6 }}>(optional)</span>
                  </label>
                  <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                    <div style={{ position: 'relative', flex: 1 }}>
                      <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
                      <input
                        className="field__input field__input--icon"
                        placeholder="e.g. 124/2"
                        value={khasraHint}
                        onChange={e => setKhasraHint(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="field__hint">
                    If provided, we'll search for a matching record. If not found, a new draft is created.
                    Leave blank to let OCR extract it automatically.
                  </div>
                </div>

                <div className="field" style={{ marginTop: 'var(--space-4)' }}>
                  <label className="field__label">Remarks</label>
                  <textarea
                    className="field__input"
                    rows={3}
                    placeholder="Optional notes for the verifier…"
                    value={remarks}
                    onChange={e => setRemarks(e.target.value)}
                  />
                </div>
              </div>
            </div>

            {errorMsg && (
              <div className="alert alert--error">
                <AlertTriangle size={14} />
                <span>
                  {errorMsg}
                  {/* Name the stage so the failure is actionable. */}
                  {failedStage && ` (failed during ${failedStage})`}
                </span>
              </div>
            )}

            <button
              type="submit"
              className="btn btn--primary btn--lg"
              style={{ width: '100%', justifyContent: 'center' }}
              disabled={!canSubmit}
            >
              <Upload size={15} /> Upload & Process Document
            </button>

            {!selected && (
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)', textAlign: 'center', lineHeight: 1.5 }}>
                Select a file first. After upload, OCR will run automatically.<br />
                You'll be taken to a review screen to verify extracted fields.
              </div>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
