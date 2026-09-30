import React, { useState } from 'react';
import { Users, Plus, CheckCircle, XCircle, Eye, Shield } from 'lucide-react';
import { MOCK_USERS } from '../mock/mockData';
import { formatRelative } from '../utils/formatters';

export function UsersPage() {
  const users = Object.values(MOCK_USERS).map(u => u.user);
  const [tab, setTab] = useState<'users'|'roles'>('users');

  const ROLES_DEF = [
    { role:'ADMIN',    desc:'Full system access — user management, settings, audit',        can:['View','Create','Verify','Admin','Export'] },
    { role:'OFFICER',  desc:'Field officer — creates and updates land records',              can:['View','Create','Upload'] },
    { role:'VERIFIER', desc:'Revenue verifier — reviews and approves/rejects records',      can:['View','Verify','Reject'] },
    { role:'VIEWER',   desc:'Read-only access for public inquiry or supervisory review',    can:['View'] },
  ];

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Users & Roles</div>
          <div className="page-hdr__sub">Manage system users and role-based access control</div>
        </div>
        {tab === 'users' && (
          <button className="btn btn--primary btn--md"><Plus size={14}/> Create User</button>
        )}
      </div>

      <div className="tabs">
        {[['users','Users'],['roles','Roles & Permissions']].map(([id,label])=>(
          <button key={id} className={`tab-btn${tab===id?' active':''}`} onClick={()=>setTab(id as any)}>
            {id==='users'?<Users size={13}/>:<Shield size={13}/>} {label}
            {id==='users' && <span className="tab-btn__count">{users.length}</span>}
          </button>
        ))}
      </div>

      {tab === 'users' && (
        <div className="tbl-wrap anim-fade-in">
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Name</th><th>Username</th><th>Email</th><th>Role</th>
                  <th>District</th><th>Status</th><th>Last Login</th><th style={{width:80}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td>
                      <div style={{ display:'flex',alignItems:'center',gap:8 }}>
                        <div style={{ width:28,height:28,borderRadius:'var(--radius-md)',background:'var(--color-navy-100)',color:'var(--color-navy-800)',fontSize:10,fontWeight:700,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0 }}>
                          {u.full_name.split(' ').map(w=>w[0]).join('').slice(0,2)}
                        </div>
                        <span style={{ fontWeight:500,fontSize:'var(--text-sm)' }}>{u.full_name}</span>
                      </div>
                    </td>
                    <td><span style={{ fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)',color:'var(--text-secondary)' }}>{u.username}</span></td>
                    <td style={{ fontSize:'var(--text-xs)',color:'var(--text-secondary)' }}>{u.email}</td>
                    <td><span className={`role-badge role-badge--${u.role}`}>{u.role}</span></td>
                    <td style={{ fontSize:'var(--text-xs)',color:'var(--text-secondary)' }}>{u.district_code ?? '—'}</td>
                    <td>
                      {u.is_active
                        ? <span style={{display:'flex',alignItems:'center',gap:4,fontSize:'var(--text-xs)',color:'var(--color-success-600)',fontWeight:500}}><CheckCircle size={12}/>Active</span>
                        : <span style={{display:'flex',alignItems:'center',gap:4,fontSize:'var(--text-xs)',color:'var(--color-error-600)',fontWeight:500}}><XCircle size={12}/>Inactive</span>
                      }
                    </td>
                    <td style={{ fontSize:'var(--text-xs)',color:'var(--text-tertiary)' }}>{u.last_login ? formatRelative(u.last_login) : 'Never'}</td>
                    <td>
                      <button className="btn btn--ghost btn--xs"><Eye size={12}/></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'roles' && (
        <div className="anim-fade-in" style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--space-4)'}}>
          {ROLES_DEF.map(r=>(
            <div key={r.role} className="card">
              <div className="card__hdr">
                <div style={{display:'flex',alignItems:'center',gap:8}}>
                  <Shield size={16} color="var(--color-navy-700)"/>
                  <span className={`role-badge role-badge--${r.role}`} style={{fontSize:12}}>{r.role}</span>
                </div>
              </div>
              <div className="card__body">
                <p style={{fontSize:'var(--text-sm)',color:'var(--text-secondary)',marginBottom:'var(--space-4)'}}>{r.desc}</p>
                <div style={{display:'flex',flexWrap:'wrap',gap:6}}>
                  {['View','Create','Verify','Reject','Admin','Upload','Export'].map(perm=>{
                    const has = r.can.includes(perm);
                    return (
                      <span key={perm} style={{display:'flex',alignItems:'center',gap:4,padding:'2px 8px',borderRadius:'var(--radius-full)',fontSize:11,fontWeight:600,background:has?'var(--color-success-50)':'var(--color-slate-100)',color:has?'var(--color-success-700)':'var(--text-tertiary)',border:`1px solid ${has?'var(--color-success-100)':'var(--border-default)'}`}}>
                        {has?<CheckCircle size={10}/>:<XCircle size={10}/>} {perm}
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
