import React, { useState } from 'react';
import { Settings, Bell, Shield, Database, Globe, Palette, Save, CheckCircle } from 'lucide-react';
import { useAuthStore } from '../store/authStore';

const TABS = [
  { id:'profile',   icon:<Settings size={13}/>,  label:'Profile' },
  { id:'notif',     icon:<Bell size={13}/>,       label:'Notifications' },
  { id:'security',  icon:<Shield size={13}/>,     label:'Security' },
  { id:'system',    icon:<Database size={13}/>,   label:'System' },
  { id:'regional',  icon:<Globe size={13}/>,      label:'Regional' },
] as const;

export function SettingsPage() {
  const { user } = useAuthStore();
  const [tab, setTab] = useState<'profile'|'notif'|'security'|'system'|'regional'>('profile');
  const [saved, setSaved] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');

  function save() { setSaved(true); setTimeout(()=>setSaved(false), 2500); }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Settings</div>
          <div className="page-hdr__sub">System configuration and personal preferences</div>
        </div>
      </div>

      <div style={{ display:'grid',gridTemplateColumns:'220px 1fr',gap:'var(--space-6)',alignItems:'start' }}>
        {/* Sidebar tabs */}
        <div className="card">
          <div style={{ padding:'var(--space-2)' }}>
            {TABS.map(t=>(
              <button key={t.id} onClick={()=>setTab(t.id)}
                className={`user-menu__item${tab===t.id?' active':''}`}
                style={{ width:'100%',borderRadius:'var(--radius-md)',background:tab===t.id?'var(--color-navy-50)':'transparent',color:tab===t.id?'var(--color-navy-800)':'var(--text-secondary)',fontWeight:tab===t.id?600:400,gap:8 }}>
                {t.icon}{t.label}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div>
          {tab === 'profile' && (
            <div className="card anim-fade-in">
              <div className="card__hdr"><div className="card__title">Personal Profile</div></div>
              <div className="card__body" style={{display:'flex',flexDirection:'column',gap:'var(--space-4)'}}>
                <div style={{display:'flex',alignItems:'center',gap:'var(--space-4)',padding:'var(--space-4)',background:'var(--color-slate-50)',borderRadius:'var(--radius-lg)',border:'1px solid var(--border-default)'}}>
                  <div style={{width:56,height:56,borderRadius:'var(--radius-xl)',background:'var(--color-navy-700)',color:'white',fontSize:20,fontWeight:700,display:'flex',alignItems:'center',justifyContent:'center'}}>
                    {user?.full_name?.split(' ').map(w=>w[0]).join('').slice(0,2)}
                  </div>
                  <div>
                    <div style={{fontWeight:700,fontSize:'var(--text-lg)'}}>{user?.full_name}</div>
                    <div style={{color:'var(--text-secondary)',fontSize:'var(--text-sm)'}}>{user?.email}</div>
                    <span className={`role-badge role-badge--${user?.role}`} style={{marginTop:4,display:'inline-block'}}>{user?.role}</span>
                  </div>
                </div>
                <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--space-4)'}}>
                  <div className="field" style={{marginBottom:0}}>
                    <label className="field__label">Full Name</label>
                    <input className="field__input" value={fullName} onChange={e=>setFullName(e.target.value)}/>
                  </div>
                  <div className="field" style={{marginBottom:0}}>
                    <label className="field__label">Email Address</label>
                    <input className="field__input" type="email" value={email} onChange={e=>setEmail(e.target.value)}/>
                  </div>
                  <div className="field" style={{marginBottom:0}}>
                    <label className="field__label">Username</label>
                    <input className="field__input" value={user?.username??''} disabled style={{background:'var(--color-slate-75)',color:'var(--text-tertiary)'}}/>
                    <div className="field__hint">Username cannot be changed</div>
                  </div>
                  <div className="field" style={{marginBottom:0}}>
                    <label className="field__label">District</label>
                    <input className="field__input" value={user?.district_code??'All Districts'} disabled style={{background:'var(--color-slate-75)',color:'var(--text-tertiary)'}}/>
                  </div>
                </div>
              </div>
              <div className="card__footer">
                {saved && <span style={{display:'flex',alignItems:'center',gap:6,fontSize:'var(--text-sm)',color:'var(--color-success-600)',fontWeight:500}}><CheckCircle size={14}/>Saved successfully</span>}
                <button className="btn btn--primary btn--md" onClick={save}><Save size={13}/>Save Changes</button>
              </div>
            </div>
          )}

          {tab === 'notif' && (
            <div className="card anim-fade-in">
              <div className="card__hdr"><div className="card__title">Notification Preferences</div></div>
              <div className="card__body">
                {[
                  ['Record verified','When a land record you submitted is verified'],
                  ['Record rejected','When a land record is rejected with remarks'],
                  ['Anomaly detected','When AI detects an anomaly on your records'],
                  ['Document processed','When an uploaded document completes processing'],
                  ['System announcements','Platform maintenance and update notices'],
                ].map(([label, desc], i) => (
                  <div key={label} style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'12px 0',borderBottom:i<4?'1px solid var(--color-slate-75)':'none'}}>
                    <div>
                      <div style={{fontSize:'var(--text-sm)',fontWeight:500}}>{label}</div>
                      <div style={{fontSize:'var(--text-xs)',color:'var(--text-secondary)'}}>{desc}</div>
                    </div>
                    <label style={{position:'relative',display:'inline-block',width:40,height:22,cursor:'pointer',flexShrink:0}}>
                      <input type="checkbox" defaultChecked={i < 4} style={{opacity:0,width:0,height:0}}/>
                      <span style={{position:'absolute',inset:0,background:i<4?'var(--color-navy-700)':'var(--color-slate-200)',borderRadius:11,transition:'0.2s'}}/>
                      <span style={{position:'absolute',top:3,left:i<4?20:3,width:16,height:16,background:'white',borderRadius:'50%',transition:'0.2s',boxShadow:'0 1px 3px rgba(0,0,0,0.2)'}}/>
                    </label>
                  </div>
                ))}
                <div style={{marginTop:'var(--space-5)',display:'flex',justifyContent:'flex-end'}}>
                  <button className="btn btn--primary btn--md" onClick={save}><Save size={13}/>Save Preferences</button>
                </div>
              </div>
            </div>
          )}

          {(tab === 'security' || tab === 'system' || tab === 'regional') && (
            <div className="card anim-fade-in">
              <div className="card__hdr"><div className="card__title">{TABS.find(t=>t.id===tab)?.label} Settings</div></div>
              <div className="card__body">
                <div className="empty" style={{padding:'var(--space-10)'}}>
                  <div className="empty__icon">⚙️</div>
                  <div className="empty__title">Settings Panel</div>
                  <div className="empty__desc">This section is available in the production deployment connected to the FastAPI backend.</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
