import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, FileText, Eye, Download, CheckCircle, XCircle,
  Clock, AlertTriangle, RefreshCw, Upload, Loader2,
} from 'lucide-react';
import {
  documentsApi, describeError,
  type DocumentListItem, type DocumentContentResponse, type ExtractedContentField,
} from '../api/documents';
import { ACTIVE_JOB_STATES, type JobState } from '../types/document';
import { formatRelative, formatFileSize } from '../utils/formatters';

const DOC_LABELS: Record<string, string> = {
  TITLE_DEED: 'Title Deed',
  SURVEY_MAP: 'Survey Map',
  MUTATION_ORDER: 'Mutation Order',
  COURT_ORDER: 'Court Order',
  TAX_RECEIPT: 'Tax Receipt',
  OTHER: 'Other',
};

const MIME_LABEL: Record<string, string> = {
  'application/pdf': 'PDF',
  'image/jpeg': 'JPG',
  'image/jpg': 'JPG',
  'image/png': 'PNG',
  'image/tiff': 'TIFF',
  'image/tif': 'TIFF',
};

function FileTypeBadge({ mime }: { mime: string | null }) {
  const label = mime ? (MIME_LABEL[mime] ?? 'DOC') : 'DOC';
  const isImg = mime?.startsWith('image/');
  return (
    <div style={{
      width: 32, height: 38,
      background: isImg ? 'var(--color-info-50)' : 'var(--color-error-50)',
      border: `1px solid ${isImg ? 'var(--color-info-100)' : 'var(--color-error-100)'}`,
      borderRadius: 4,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 8, fontWeight: 700,
      color: isImg ? 'var(--color-info-600)' : 'var(--color-error-600)',
      flexShrink: 0,
    }}>
      {label}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const color =
    value >= 85 ? 'var(--color-success-500)' :
    value >= 65 ? 'var(--color-warning-500)' : 'var(--color-error-500)';
  return (
    <div className="confidence">
      <div className="confidence__bar">
        <div className="confidence__fill" style={{ width: `${value}%`, background: color }} />
      </div>
      <span className="confidence__val" style={{ color }}>{value}%</span>
    </div>
  );
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  UPLOADED:   <Clock size={13} color="var(--color-warning-600)" />,
  PROCESSING: <Loader2 size={13} color="var(--color-info-600)" className="spin" />,
  VALIDATED:  <CheckCircle size={13} color="var(--color-success-600)" />,
  REJECTED:   <XCircle size={13} color="var(--color-error-600)" />,
};

/** One extracted field as a row in the details modal. */
function ExtractedFieldRow({ field }: { field: ExtractedContentField }) {
  const value = field.verified_value ?? field.normalized_value ?? field.raw_value;
  const reviewed = field.needs_review;

  return (
    <tr>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
          {field.field_display ?? field.field_name}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
          {field.field_name}
          {field.source_page != null && ` · page ${field.source_page}`}
        </div>
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border-subtle)', fontSize: 'var(--text-sm)' }}>
        {value
          ? <span style={{ color: 'var(--text-primary)' }}>{value}</span>
          : <span style={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>not found</span>}
        {field.verified_value && field.normalized_value && field.verified_value !== field.normalized_value && (
          <div style={{ fontSize: 10, color: 'var(--color-success-600)' }}>
            verified as {field.verified_value}
          </div>
        )}
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border-subtle)', width: 90 }}>
        <ConfidenceBar value={field.confidence_pct} />
      </td>
      <td style={{ padding: '6px 8px', borderBottom: '1px solid var(--border-subtle)', width: 110 }}>
        {reviewed ? (
          <span className="badge badge--warning">needs review</span>
        ) : (
          <span className="badge badge--success">{String(field.validation_status).toLowerCase()}</span>
        )}
      </td>
    </tr>
  );
}

/**
 * "View details" modal: everything the pipeline read out of one document.
 *
 * Shows the document header, the linked land record, every extracted field with
 * its confidence and validation state, and the raw per-field OCR reads. Renders
 * explicit empty states for a document that was never processed rather than an
 * empty table that looks like a failure.
 */
function DocumentDetailsModal({
  content, loading, error, onClose, onDownload, downloading,
}: {
  content: DocumentContentResponse | null;
  loading: boolean;
  error: string;
  onClose: () => void;
  onDownload: () => void;
  downloading: boolean;
}) {
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const fields = content?.extracted_fields ?? [];
  const record = content?.land_record;
  const job = content?.pipeline_job;
  const processed = fields.length > 0;

  return (
    <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal modal--xl" style={{ maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}>
        <div className="modal__hdr">
          <span className="modal__title">
            {content?.document.original_filename ?? 'Document details'}
          </span>
          <button className="modal__close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        <div className="modal__body">
          {loading && (
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
              <Loader2 size={14} className="spin" /> Loading extracted content…
            </div>
          )}

          {!loading && error && (
            <div className="alert alert--error">
              <XCircle size={13} /><span>{error}</span>
            </div>
          )}

          {!loading && !error && content && (
            <>
              {/* Document header */}
              <div style={{ display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap', marginBottom: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Type</div>
                  <div>{DOC_LABELS[content.document.document_type] ?? content.document.document_type}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Status</div>
                  <div>{content.document.status}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Size</div>
                  <div>
                    {content.document.file_size_bytes != null
                      ? formatFileSize(content.document.file_size_bytes)
                      : '—'}
                  </div>
                </div>
                {job?.confidence != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Confidence</div>
                    <div><ConfidenceBar value={job.confidence} /></div>
                  </div>
                )}
                {job?.detected_language && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Language</div>
                    <div>{job.detected_language}</div>
                  </div>
                )}
                {job?.page_count != null && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Pages</div>
                    <div>{job.page_count}</div>
                  </div>
                )}
              </div>

              {/* Linked land record */}
              {record && (
                <div style={{ background: 'var(--color-info-50)', border: '1px solid var(--color-info-100)', borderRadius: 6, padding: 'var(--space-3)', marginBottom: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginBottom: 4 }}>Saved to land record</div>
                  <strong>{record.khasra_number}</strong>
                  {record.owner_name && ` · ${record.owner_name}`}
                  {record.village && ` · ${record.village}`}
                  {record.area_hectares != null && ` · ${record.area_hectares} ha`}
                </div>
              )}

              {/* Extracted fields */}
              {processed ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-2)' }}>
                    <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>
                      Extracted content ({fields.length} field{fields.length === 1 ? '' : 's'})
                    </span>
                    {content.raw_ocr_text && (
                      <button
                        className="btn btn--ghost btn--xs"
                        onClick={() => setShowRaw(v => !v)}
                      >
                        <FileText size={12} /> {showRaw ? 'Hide' : 'Show'} raw reads
                      </button>
                    )}
                  </div>

                  {showRaw && content.raw_ocr_text && (
                    <pre style={{
                      background: 'var(--color-slate-900)', color: 'var(--color-slate-100)',
                      padding: 'var(--space-3)', borderRadius: 6, fontSize: 11,
                      maxHeight: 200, overflow: 'auto', whiteSpace: 'pre-wrap',
                      marginBottom: 'var(--space-3)',
                    }}>
                      {content.raw_ocr_text}
                    </pre>
                  )}

                  <table className="table" style={{ width: '100%' }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left', padding: '6px 8px' }}>Field</th>
                        <th style={{ textAlign: 'left', padding: '6px 8px' }}>Extracted value</th>
                        <th style={{ textAlign: 'left', padding: '6px 8px' }}>Confidence</th>
                        <th style={{ textAlign: 'left', padding: '6px 8px' }}>Validation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.map(f => <ExtractedFieldRow key={f.id} field={f} />)}
                    </tbody>
                  </table>
                </>
              ) : (
                <div className="alert alert--warning">
                  <AlertTriangle size={13} />
                  <span>
                    {job
                      ? 'No fields were extracted from this document. Check the pipeline status for the failure reason.'
                      : 'This document has not been processed yet, so there is no extracted content. Use “Reprocess” to run it through the pipeline.'}
                  </span>
                </div>
              )}

              {content.document.validation_notes && (
                <div style={{ marginTop: 'var(--space-4)', fontSize: 'var(--text-sm)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>Validation notes</div>
                  {content.document.validation_notes}
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal__footer">
          <button className="btn btn--secondary btn--md" onClick={onClose}>Close</button>
          <button
            className="btn btn--primary btn--md"
            onClick={onDownload}
            disabled={downloading || !content?.document.file_available}
            title={content && !content.document.file_available ? 'The stored file is no longer on the server' : undefined}
          >
            {downloading
              ? <Loader2 size={13} className="spin" />
              : <Download size={13} />}
            Download original
          </button>
        </div>
      </div>
    </div>
  );
}

export function DocumentsPage() {
  const navigate = useNavigate();
  const [items, setItems]       = useState<DocumentListItem[]>([]);
  const [total, setTotal]       = useState(0);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState('');
  const [q, setQ]               = useState('');
  const [typeF, setTypeF]       = useState('');
  const [statusF, setStatusF]   = useState('');
  const [page, setPage]         = useState(1);

  // "View details" modal
  const [viewing, setViewing]       = useState<DocumentListItem | null>(null);
  const [viewContent, setViewContent] = useState<DocumentContentResponse | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewError, setViewError]   = useState('');
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const PAGE_SIZE = 50;

  const openDetails = useCallback(async (doc: DocumentListItem) => {
    setViewing(doc);
    setViewContent(null);
    setViewError('');
    setViewLoading(true);
    try {
      setViewContent(await documentsApi.documentContent(doc.id));
    } catch (err) {
      setViewError(describeError(err));
    } finally {
      setViewLoading(false);
    }
  }, []);

  const download = useCallback(async (doc: DocumentListItem) => {
    setDownloadingId(doc.id);
    try {
      await documentsApi.downloadDocument(doc.id, doc.original_filename);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setDownloadingId(null);
    }
  }, []);

  const load = useCallback(async (pg = 1, search = q, dType = typeF, dStatus = statusF) => {
    setLoading(true);
    setError('');
    try {
      const res = await documentsApi.list({
        page: pg,
        page_size: PAGE_SIZE,
        search: search || undefined,
        document_type: dType || undefined,
        status: dStatus || undefined,
      });
      setItems(res.items);
      setTotal(res.total);
      setPage(pg);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, [q, typeF, statusF]);

  // Initial load
  useEffect(() => { void load(1, '', '', ''); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    void load(1);
  }

  function handleTypeChange(v: string) {
    setTypeF(v);
    void load(1, q, v, statusF);
  }

  function handleStatusChange(v: string) {
    setStatusF(v);
    void load(1, q, typeF, v);
  }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Documents</div>
          <div className="page-hdr__sub">
            {loading ? 'Loading…' : `${total} document${total !== 1 ? 's' : ''} in system`}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn--ghost btn--md" onClick={() => void load(page)} title="Refresh">
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
          <button className="btn btn--primary btn--md" onClick={() => navigate('/intake')}>
            <Upload size={14} /> Upload Document
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          <AlertTriangle size={14} /><span>{error}</span>
        </div>
      )}

      <div className="tbl-wrap">
        <form className="tbl-toolbar" onSubmit={handleSearch}>
          <div style={{ position: 'relative', flex: '1', maxWidth: 320 }}>
            <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
            <input
              className="field__input field__input--icon"
              placeholder="Search filename, khasra, owner…"
              value={q}
              onChange={e => setQ(e.target.value)}
              onBlur={() => void load(1)}
            />
          </div>
          <select className="field__input" style={{ width: 170 }} value={typeF} onChange={e => handleTypeChange(e.target.value)}>
            <option value="">All Types</option>
            {Object.entries(DOC_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select className="field__input" style={{ width: 155 }} value={statusF} onChange={e => handleStatusChange(e.target.value)}>
            <option value="">All Statuses</option>
            {['UPLOADED', 'PROCESSING', 'VALIDATED', 'REJECTED'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="submit" className="btn btn--secondary btn--md">
            <Search size={13} /> Search
          </button>
        </form>

        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Document</th>
                <th>Type</th>
                <th>Khasra No.</th>
                <th>Owner</th>
                <th>Size</th>
                <th>Status</th>
                <th>Confidence</th>
                <th>Uploaded</th>
                <th style={{ width: 80 }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && items.length === 0 ? (
                <tr><td colSpan={9}>
                  <div className="empty">
                    <Loader2 size={24} className="spin" style={{ margin: '0 auto var(--space-3)', display: 'block', color: 'var(--color-navy-400)' }} />
                    <div className="empty__title">Loading documents…</div>
                  </div>
                </td></tr>
              ) : items.length === 0 ? (
                <tr><td colSpan={9}>
                  <div className="empty">
                    <div className="empty__icon">📄</div>
                    <div className="empty__title">No documents found</div>
                    <div className="empty__sub">
                      {q || typeF || statusF
                        ? 'No documents match your filters.'
                        : 'Upload a document from Document Intake to get started.'}
                    </div>
                    {!q && !typeF && !statusF && (
                      <button className="btn btn--primary btn--md" style={{ marginTop: 'var(--space-4)' }} onClick={() => navigate('/intake')}>
                        <Upload size={14} /> Upload First Document
                      </button>
                    )}
                  </div>
                </td></tr>
              ) : (
                items.map(doc => (
                  <tr key={doc.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <FileTypeBadge mime={doc.mime_type} />
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--text-primary)' }} className="truncate">
                            {doc.original_filename}
                          </div>
                          {doc.uploader_username && (
                            <div style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
                              by {doc.uploader_username}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="badge" style={{ background: 'var(--color-slate-100)', color: 'var(--text-secondary)' }}>
                        {DOC_LABELS[doc.document_type] ?? doc.document_type}
                      </span>
                    </td>
                    <td>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--color-navy-700)' }}>
                        {doc.khasra_number}
                      </span>
                    </td>
                    <td style={{ fontSize: 'var(--text-xs)' }}>{doc.owner_name}</td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>
                      {doc.file_size_bytes ? formatFileSize(doc.file_size_bytes) : '—'}
                    </td>
                    <td>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 'var(--text-xs)', fontWeight: 500 }}>
                        {STATUS_ICONS[doc.status] ?? null} {doc.status}
                      </span>
                      {/* Show the real pipeline stage, not just the upload status,
                          so a queued or running job is visible from this list. */}
                      {doc.processing_status === 'failed' ? (
                        <div style={{ fontSize: 10, color: 'var(--color-danger-600)', marginTop: 2 }}>
                          failed{doc.failed_stage ? ` at ${doc.failed_stage.replace(/_/g, ' ').toLowerCase()}` : ''}
                        </div>
                      ) : doc.needs_human_review ? (
                        <div style={{ fontSize: 10, color: 'var(--color-warning-600)', marginTop: 2 }}>
                          needs verification
                        </div>
                      ) : ACTIVE_JOB_STATES.has(doc.processing_status as JobState) ? (
                        <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>
                          {String(doc.current_stage ?? '').replace(/_/g, ' ').toLowerCase()}
                          {doc.progress_pct ? ` · ${doc.progress_pct}%` : ''}
                        </div>
                      ) : null}
                    </td>
                    <td style={{ minWidth: 130 }}>
                      {doc.confidence != null
                        ? <ConfidenceBar value={doc.confidence} />
                        : <span style={{ color: 'var(--text-tertiary)', fontSize: 11 }}>—</span>}
                    </td>
                    <td style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>
                      {formatRelative(doc.created_at)}
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 2 }}>
                        <button
                          className="btn btn--ghost btn--xs"
                          title="View details"
                          onClick={() => void openDetails(doc)}
                        >
                          <Eye size={12} />
                        </button>
                        <button
                          className="btn btn--ghost btn--xs"
                          title="Download"
                          aria-label={`Download ${doc.original_filename}`}
                          disabled={downloadingId === doc.id}
                          onClick={() => void download(doc)}
                        >
                          {downloadingId === doc.id
                            ? <Loader2 size={12} className="spin" />
                            : <Download size={12} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > PAGE_SIZE && (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-3)', padding: 'var(--space-4)', borderTop: '1px solid var(--border-default)' }}>
            <button
              className="btn btn--secondary btn--sm"
              disabled={page <= 1 || loading}
              onClick={() => void load(page - 1)}
            >
              ← Prev
            </button>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
              Page {page} of {Math.ceil(total / PAGE_SIZE)}
            </span>
            <button
              className="btn btn--secondary btn--sm"
              disabled={page >= Math.ceil(total / PAGE_SIZE) || loading}
              onClick={() => void load(page + 1)}
            >
              Next →
            </button>
          </div>
        )}
      </div>

      {viewing && (
        <DocumentDetailsModal
          content={viewContent}
          loading={viewLoading}
          error={viewError}
          downloading={downloadingId === viewing.id}
          onClose={() => setViewing(null)}
          onDownload={() => void download(viewing)}
        />
      )}
    </div>
  );
}
