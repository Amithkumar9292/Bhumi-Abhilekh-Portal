import React, { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { getMockAuditEvents } from '../mock/mockData';
import { formatDateTime, formatRelative } from '../utils/formatters';

const ACTION_ICONS: Record<string, string> = {
  LOGIN:'🔐', CREATE_RECORD:'📝', VERIFY_RECORD:'✅', REJECT_RECORD:'❌',
  UPLOAD_DOCUMENT:'📄', VALIDATE_DOCUMENT:'🔍', UPDATE_RECORD:'✏️', EXPORT_REPORT:'📊',
};

export function AuditTrailPage() {
  const all = useMemo(() => getMockAuditEvents(), []);
  const [q, setQ] = useState('');
  const [actionF, setActionF] = useState('');
  const [roleF, setRoleF] = useState('');

  const filtered = useMemo(() => {
    let d = all;
    if (q) { const ql=q.toLowerCase(); d=d.filter(e=>e.actor.toLowerCase().includes(ql)||e.action.toLowerCase().includes(ql)||e.resource_id.toLowerCase().includes(ql)); }
    if (actionF) d = d.filter(e => e.action === actionF);
    if (roleF)   d = d.filter(e => e.actor_role === roleF);
    return d;
  }, [all, q, actionF, roleF]);

  const uniqueActions = [...new Set(all.map(e => e.action))];

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Audit Trail</div>
          <div className="page-hdr__sub">Complete immutable record of all system actions</div>
        </div>
        <button className="btn btn--secondary btn--md">Export CSV</button>
      </div>

      <div className="tbl-wrap">
        <div className="tbl-toolbar">
          <div style={{ position:'relative', flex:'1', maxWidth:280 }}>
            <Search size={13} style={{position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',color:'var(--text-tertiary)',pointerEvents:'none'}}/>
            <input className="field__input field__input--icon" placeholder="Search actor, action, resource…"
              value={q} onChange={e=>setQ(e.target.value)}/>
          </div>
          <select className="field__input" style={{width:180}} value={actionF} onChange={e=>setActionF(e.target.value)}>
            <option value="">All Actions</option>
            {uniqueActions.map(a=><option key={a} value={a}>{a.replace(/_/g,' ')}</option>)}
          </select>
          <select className="field__input" style={{width:130}} value={roleF} onChange={e=>setRoleF(e.target.value)}>
            <option value="">All Roles</option>
            {['ADMIN','OFFICER','VERIFIER','VIEWER'].map(r=><option key={r} value={r}>{r}</option>)}
          </select>
          <span style={{marginLeft:'auto',fontSize:'var(--text-xs)',color:'var(--text-secondary)'}}>{filtered.length} events</span>
        </div>

        <div className="tbl-scroll">
          <table className="tbl">
            <thead>
              <tr>
                <th>Timestamp</th><th>Action</th><th>Actor</th><th>Role</th>
                <th>Resource</th><th>Description</th><th>Status</th><th>IP</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0,60).map(e => (
                <tr key={e.id}>
                  <td>
                    <div style={{fontSize:'var(--text-xs)',color:'var(--text-primary)',fontFamily:'var(--font-mono)',whiteSpace:'nowrap'}}>{formatDateTime(e.timestamp)}</div>
                    <div style={{fontSize:10,color:'var(--text-tertiary)'}}>{formatRelative(e.timestamp)}</div>
                  </td>
                  <td>
                    <span style={{display:'flex',alignItems:'center',gap:6,fontSize:'var(--text-xs)',whiteSpace:'nowrap'}}>
                      <span>{ACTION_ICONS[e.action]??'⚙️'}</span>
                      <code style={{background:'var(--color-slate-100)',padding:'1px 6px',borderRadius:'var(--radius-xs)',fontSize:11,fontFamily:'var(--font-mono)',color:'var(--color-navy-800)'}}>{e.action}</code>
                    </span>
                  </td>
                  <td style={{fontWeight:500,fontSize:'var(--text-xs)'}}>{e.actor}</td>
                  <td><span className={`role-badge role-badge--${e.actor_role}`}>{e.actor_role}</span></td>
                  <td>
                    <div style={{fontSize:'var(--text-xs)',color:'var(--text-secondary)'}}>{e.resource_type}</div>
                    <div style={{fontSize:11,fontFamily:'var(--font-mono)',color:'var(--text-tertiary)'}}>{e.resource_id}</div>
                  </td>
                  <td style={{fontSize:'var(--text-xs)',color:'var(--text-secondary)',maxWidth:200}}>{e.description}</td>
                  <td>
                    <span style={{display:'flex',alignItems:'center',gap:4,fontSize:11,fontWeight:600,color:e.status==='SUCCESS'?'var(--color-success-600)':'var(--color-error-600)'}}>
                      <span style={{width:6,height:6,borderRadius:'50%',background:e.status==='SUCCESS'?'var(--color-success-500)':'var(--color-error-500)'}}/>
                      {e.status}
                    </span>
                  </td>
                  <td style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--text-tertiary)',whiteSpace:'nowrap'}}>{e.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
