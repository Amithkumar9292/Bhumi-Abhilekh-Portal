import React, { useState } from 'react';
import { CheckCircle, XCircle, Clock, Eye, ChevronDown } from 'lucide-react';
import { getVerificationQueue } from '../mock/mockData';
import { formatRelative, STATUS_LABELS, LAND_USE_LABELS } from '../utils/formatters';

export function VerificationPage() {
  const queue = getVerificationQueue();
  const [active, setActive] = useState<string|null>(null);
  const [decisions, setDecisions] = useState<Record<string,{action:'approve'|'reject';note:string}>>({});
  const [note, setNote] = useState('');
  const [filter, setFilter] = useState<'ALL'|'PENDING'|'UNDER_REVIEW'>('ALL');

  const filtered = queue.filter(r => filter === 'ALL' || r.status === filter);
  const selected = queue.find(r => r.id === active);

  function decide(id:string, action:'approve'|'reject') {
    setDecisions(d => ({...d,[id]:{action,note}}));
    setNote('');
    setActive(null);
  }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Verification Queue</div>
          <div className="page-hdr__sub">{queue.length} records awaiting review</div>
        </div>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'380px 1fr',gap:'var(--space-5)',alignItems:'start'}}>
        {/* Queue list */}
        <div className="card" style={{position:'sticky',top:'calc(var(--topbar-height) + var(--header-height) + var(--nav-height) + var(--space-4))'}}>
          <div className="card__hdr">
            <div className="card__title">Queue</div>
            <select className="field__input" style={{width:140,height:28,fontSize:'var(--text-xs)'}} value={filter} onChange={e=>setFilter(e.target.value as any)}>
              <option value="ALL">All Pending</option>
              <option value="PENDING">New Submissions</option>
              <option value="UNDER_REVIEW">Under Review</option>
            </select>
          </div>
          <div style={{maxHeight:'65vh',overflowY:'auto'}}>
            {filtered.map(r => {
              const dec = decisions[r.id];
              return (
                <div key={r.id}
                  onClick={() => setActive(r.id === active ? null : r.id)}
                  style={{padding:'12px 16px',borderBottom:'1px solid var(--color-slate-75)',cursor:'pointer',
                    background: r.id===active ? 'var(--color-navy-50)' : dec ? 'var(--color-slate-50)' : 'white',
                    borderLeft: r.id===active ? '3px solid var(--color-navy-700)' : '3px solid transparent',
                    transition:'all var(--transition-fast)',
                  }}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:4}}>
                    <span style={{fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)',fontWeight:700,color:'var(--color-navy-700)'}}>{r.khasra_number}</span>
                    {dec ? (
                      <span style={{display:'flex',alignItems:'center',gap:4,fontSize:11,color:dec.action==='approve'?'var(--color-success-600)':'var(--color-error-600)',fontWeight:600}}>
                        {dec.action==='approve'?<CheckCircle size={11}/>:<XCircle size={11}/>}
                        {dec.action==='approve'?'Approved':'Rejected'}
                      </span>
                    ) : <span className={`badge badge--${r.status}`}>{STATUS_LABELS[r.status]}</span>}
                  </div>
                  <div style={{fontSize:'var(--text-sm)',fontWeight:500,color:'var(--text-primary)',marginBottom:2}}>{r.owner_name}</div>
                  <div style={{display:'flex',gap:8,fontSize:11,color:'var(--text-secondary)'}}>
                    <span>{r.district}</span>·<span>{r.area_hectares} ha</span>·<span>{formatRelative(r.created_at)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Detail + Action */}
        {selected ? (
          <div className="anim-fade-in">
            <div className="card" style={{marginBottom:'var(--space-4)'}}>
              <div className="card__hdr">
                <div>
                  <div className="card__title">{selected.khasra_number}</div>
                  <div className="card__sub">{selected.village}, {selected.tehsil}, {selected.district}</div>
                </div>
                <span className={`badge badge--${selected.status}`}>{STATUS_LABELS[selected.status]}</span>
              </div>
              <div className="card__body">
                <div className="info-grid">
                  {[
                    ['Owner',selected.owner_name],['Father/Spouse',selected.father_name],
                    ['Khasra No.',selected.khasra_number],['Khatauni No.',selected.khatauni_number],
                    ['Area',`${selected.area_hectares} ha`],['Land Use',LAND_USE_LABELS[selected.land_use_type]??selected.land_use_type],
                    ['State',selected.state],['District',selected.district],
                    ['Tehsil',selected.tehsil],['Village',selected.village],
                    ['Address',selected.address||'—'],['Survey No.',selected.survey_number],
                  ].map(([l,v])=>(
                    <div className="info-row" key={String(l)}>
                      <div className="info-row__label">{l}</div>
                      <div className="info-row__value">{v||'—'}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Action panel */}
            {!decisions[selected.id] && (
              <div className="card">
                <div className="card__hdr"><div className="card__title">Verification Decision</div></div>
                <div className="card__body">
                  <div className="field">
                    <label className="field__label">Remarks (optional for approval, required for rejection)</label>
                    <textarea className="field__input" rows={3} placeholder="Enter your verification notes…"
                      value={note} onChange={e=>setNote(e.target.value)}/>
                  </div>
                  <div style={{display:'flex',gap:'var(--space-3)'}}>
                    <button className="btn btn--success btn--md" style={{flex:1,justifyContent:'center'}}
                      onClick={()=>decide(selected.id,'approve')}>
                      <CheckCircle size={14}/> Approve Record
                    </button>
                    <button className="btn btn--danger btn--md" style={{flex:1,justifyContent:'center'}}
                      disabled={!note}
                      onClick={()=>decide(selected.id,'reject')}>
                      <XCircle size={14}/> Reject Record
                    </button>
                  </div>
                </div>
              </div>
            )}
            {decisions[selected.id] && (
              <div className={`alert alert--${decisions[selected.id].action==='approve'?'success':'error'}`}>
                {decisions[selected.id].action==='approve'?<CheckCircle size={14}/>:<XCircle size={14}/>}
                <span>Record <strong>{decisions[selected.id].action==='approve'?'approved':'rejected'}</strong> in this session. Changes will be saved on sync.</span>
              </div>
            )}
          </div>
        ) : (
          <div className="empty" style={{background:'var(--bg-surface)',border:'1px solid var(--border-default)',borderRadius:'var(--radius-xl)'}}>
            <div className="empty__icon">👈</div>
            <div className="empty__title">Select a record to review</div>
            <div className="empty__desc">Click any record from the queue to view its full details and make a verification decision.</div>
          </div>
        )}
      </div>
    </div>
  );
}
