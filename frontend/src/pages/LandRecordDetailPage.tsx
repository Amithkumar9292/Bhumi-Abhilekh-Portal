import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, XCircle, Edit, Trash2, MapPin, Calendar, User, Hash, Layers, AlertTriangle } from 'lucide-react';
import { landRecordsApi } from '../api/landRecords';
import { useAuthStore } from '../store/authStore';
import { formatDateTime, formatArea, LAND_USE_LABELS, STATUS_LABELS } from '../utils/formatters';
import { describeApiError } from '../utils/errors';
import type { LandRecord, RecordStatus } from '../types/land';

function StatusBadge({ status }: { status: RecordStatus }) {
  return <span className={`badge badge--${status}`}>{STATUS_LABELS[status]}</span>;
}

/** Statuses the backend's /verify endpoint will accept (land_records.py). */
const VERIFIABLE: RecordStatus[] = ['PENDING', 'UNDER_REVIEW'];

export function LandRecordDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [record, setRecord] = useState<LandRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectNote, setRejectNote] = useState('');
  const [toastMsg, setToastMsg] = useState('');

  const canVerify = user?.role === 'VERIFIER' || user?.role === 'ADMIN';
  const canEdit = user?.role === 'OFFICER' || user?.role === 'ADMIN';

  // Fetch by id. This page is reached from "Confirm & Save" and from the
  // completed-record panel, so the id is always a real database id -- it will
  // never be one of the seeded demo rows.
  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setLoadError('');
    try {
      setRecord(await landRecordsApi.get(id));
    } catch (err) {
      setRecord(null);
      setLoadError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  function toast(msg: string) {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(''), 2500);
  }

  /**
   * Persist the decision. The previous version only flipped local state, so an
   * approver saw a success toast while the record stayed unverified in the
   * database. The server response is the new source of truth.
   */
  async function decide(approved: boolean, rejectionReason?: string) {
    if (!id) return;
    setBusy(true);
    setActionError('');
    try {
      const updated = await landRecordsApi.verify(id, { approved, rejection_reason: rejectionReason });
      setRecord(updated);
      setShowRejectModal(false);
      setRejectNote('');
      toast(approved ? 'Record approved and marked as Verified' : 'Record rejected');
    } catch (err) {
      setActionError(describeApiError(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="empty" style={{ marginTop: 'var(--space-16)' }}>
        <div className="empty__icon">⏳</div>
        <div className="empty__title">Loading Record</div>
        <div className="empty__desc">Fetching record {id}…</div>
      </div>
    );
  }

  if (!record) {
    return (
      <div className="empty" style={{ marginTop: 'var(--space-16)' }}>
        <div className="empty__icon">🔍</div>
        <div className="empty__title">Record Not Found</div>
        <div className="empty__desc">
          {loadError
            ? `Could not load record "${id}": ${loadError}`
            : `The record ID "${id}" does not exist.`}
        </div>
        <Link to="/land-records" className="btn btn--primary btn--md" style={{ marginTop: 'var(--space-4)' }}>
          ← Back to Land Records
        </Link>
      </div>
    );
  }

  const currentStatus = record.status;
  const verifiable = VERIFIABLE.includes(currentStatus);

  return (
    <div className="anim-fade-up">
      {/* Toast */}
      {toastMsg && (
        <div className="toast-stack">
          <div className="toast toast--success"><CheckCircle size={14} color="var(--color-success-600)"/><div className="toast__content"><div className="toast__title">{toastMsg}</div></div></div>
        </div>
      )}

      {/* Breadcrumb */}
      <div className="breadcrumbs">
        <Link to="/land-records" className="breadcrumbs__item breadcrumbs__item--link">Land Records</Link>
        <span className="breadcrumbs__sep">/</span>
        <span className="breadcrumbs__item breadcrumbs__item--active">{record.khasra_number}</span>
      </div>

      <div className="page-hdr">
        <div style={{ display:'flex', alignItems:'center', gap:'var(--space-3)' }}>
          <button className="btn btn--ghost btn--sm" onClick={() => navigate(-1)}><ArrowLeft size={13}/></button>
          <div>
            <div className="page-hdr__title" style={{ display:'flex', alignItems:'center', gap:'var(--space-3)' }}>
              {record.khasra_number}
              <StatusBadge status={currentStatus}/>
            </div>
            <div className="page-hdr__sub">{record.village}, {record.tehsil}, {record.district} · {record.state}</div>
          </div>
        </div>
        <div className="page-hdr__actions">
          {canEdit && <button className="btn btn--secondary btn--sm" onClick={() => toast('Editing is not available in this build')}><Edit size={13}/> Edit</button>}
          {canVerify && verifiable && <>
            <button className="btn btn--success btn--sm" disabled={busy} onClick={() => decide(true)}><CheckCircle size={13}/> Approve</button>
            <button className="btn btn--danger btn--sm" disabled={busy} onClick={() => setShowRejectModal(true)}><XCircle size={13}/> Reject</button>
          </>}
          {user?.role === 'ADMIN' && <button className="btn btn--ghost btn--sm" style={{color:'var(--color-error-600)'}}><Trash2 size={13}/></button>}
        </div>
      </div>

      {actionError && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          <AlertTriangle size={14}/>
          <div>{actionError}</div>
        </div>
      )}

      <div style={{ display:'grid', gridTemplateColumns:'1fr 320px', gap:'var(--space-5)', alignItems:'start' }}>
        {/* Main details */}
        <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-4)' }}>
          {/* Property info */}
          <div className="card">
            <div className="card__hdr">
              <div className="card__title"><MapPin size={14} style={{marginRight:4}}/>Property Information</div>
            </div>
            <div className="card__body">
              <div className="info-grid">
                {[
                  ['Khasra Number', record.khasra_number], ['Khatauni Number', record.khatauni_number],
                  ['Survey Number', record.survey_number], ['Area', formatArea(record.area_hectares)],
                  ['Land Use', LAND_USE_LABELS[record.land_use_type] ?? record.land_use_type], ['PIN Code', record.pin_code],
                  ['State', record.state], ['District', record.district],
                  ['Tehsil', record.tehsil], ['Village', record.village],
                ].map(([l, v]) => (
                  <div className="info-row" key={String(l)}>
                    <div className="info-row__label">{l}</div>
                    <div className={`info-row__value${['Khasra Number','Khatauni Number','Survey Number'].includes(l as string)?' info-row__value--mono':''}`}>{v ?? '—'}</div>
                  </div>
                ))}
                <div className="info-row" style={{ gridColumn:'1/-1' }}>
                  <div className="info-row__label">Address</div>
                  <div className="info-row__value">{record.address || '—'}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Owner info */}
          <div className="card">
            <div className="card__hdr">
              <div className="card__title"><User size={14} style={{marginRight:4}}/>Owner Information</div>
            </div>
            <div className="card__body">
              <div className="info-grid">
                {[['Owner Name', record.owner_name], ['Father / Spouse', record.father_name], ['Aadhaar (Last 4)', record.aadhaar_last4 ? '••••' + record.aadhaar_last4 : null]].map(([l, v]) => (
                  <div className="info-row" key={String(l)}>
                    <div className="info-row__label">{l}</div>
                    <div className="info-row__value">{v || '—'}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {currentStatus === 'REJECTED' && (
            <div className="alert alert--error">
              <AlertTriangle size={14}/>
              <div><strong>Rejection Reason:</strong> {record.rejection_reason || 'No reason provided'}</div>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div style={{ display:'flex', flexDirection:'column', gap:'var(--space-4)' }}>
          <div className="card">
            <div className="card__hdr"><div className="card__title"><Calendar size={13} style={{marginRight:4}}/>Timeline</div></div>
            <div className="card__body">
              <div className="timeline">
                <div className="timeline-item">
                  <div className="timeline-item__dot timeline-item__dot--info"><Hash size={12} color="var(--color-info-600)"/></div>
                  <div className="timeline-item__body">
                    <div className="timeline-item__title">Record Created</div>
                    <div className="timeline-item__sub">by {record.created_by}</div>
                    <div className="timeline-item__time">{formatDateTime(record.created_at)}</div>
                  </div>
                </div>
                <div className="timeline-item">
                  <div className="timeline-item__dot" style={{background:'var(--color-warning-100)'}}><Layers size={12} color="var(--color-warning-600)"/></div>
                  <div className="timeline-item__body">
                    <div className="timeline-item__title">Last Updated</div>
                    <div className="timeline-item__time">{formatDateTime(record.updated_at)}</div>
                  </div>
                </div>
                {record.verified_at && (
                  <div className="timeline-item">
                    <div className="timeline-item__dot timeline-item__dot--success"><CheckCircle size={12} color="var(--color-success-600)"/></div>
                    <div className="timeline-item__body">
                      <div className="timeline-item__title">Verified</div>
                      <div className="timeline-item__sub">by {record.verified_by}</div>
                      <div className="timeline-item__time">{formatDateTime(record.verified_at)}</div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="card">
            <div className="card__hdr"><div className="card__title">System Info</div></div>
            <div className="card__body">
              {[['Record ID', record.id], ['Status', STATUS_LABELS[currentStatus]]].map(([l,v])=>(
                <div className="info-row" key={String(l)}>
                  <div className="info-row__label">{l}</div>
                  <div className={`info-row__value${l==='Record ID'?' info-row__value--mono':''}`} style={{fontSize:l==='Record ID'?11:'var(--text-sm)'}}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Reject modal */}
      {showRejectModal && (
        <div className="modal-overlay" onClick={e=>{ if(e.target===e.currentTarget) setShowRejectModal(false); }}>
          <div className="modal modal--md">
            <div className="modal__hdr">
              <span className="modal__title">Reject Record</span>
              <button className="modal__close" onClick={()=>setShowRejectModal(false)}>✕</button>
            </div>
            <div className="modal__body">
              <div className="alert alert--warning" style={{marginBottom:'var(--space-4)'}}><AlertTriangle size={13}/><span>Rejection is recorded in the audit trail and cannot be undone without re-submission.</span></div>
              <div className="field">
                <label className="field__label field__label--req">Rejection Reason</label>
                <textarea className="field__input" rows={4} placeholder="Provide specific reason for rejection…"
                  value={rejectNote} onChange={e=>setRejectNote(e.target.value)}/>
              </div>
            </div>
            <div className="modal__footer">
              <button className="btn btn--secondary btn--md" onClick={()=>setShowRejectModal(false)}>Cancel</button>
              <button className="btn btn--danger btn--md" disabled={!rejectNote || busy} onClick={() => decide(false, rejectNote)}><XCircle size={13}/>Confirm Rejection</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
