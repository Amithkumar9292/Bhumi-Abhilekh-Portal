import React from 'react';
import { CheckCircle, XCircle, AlertTriangle, ExternalLink } from 'lucide-react';

const INTEGRATIONS = [
  { id:'dilrmp',  name:'DILRMP Portal',       desc:'Department of Land Resources — Ministry of Rural Development', status:'connected', lastSync:'2 hours ago', type:'Government API' },
  { id:'aadhaar', name:'Aadhaar OTP Auth',    desc:'UIDAI biometric verification gateway for owner identity',      status:'connected', lastSync:'Live',       type:'Identity' },
  { id:'census',  name:'Census GIS Data',     desc:'SoI Topographic maps and administrative boundary datasets',    status:'connected', lastSync:'24 hours ago',type:'Geospatial' },
  { id:'nlrmp',   name:'NLRMP Database',      desc:'National Land Records Management Programme data sync',         status:'warning',   lastSync:'6 hours ago', type:'Government API' },
  { id:'smtp',    name:'Email Gateway',        desc:'Government SMTP relay for notifications and OTP delivery',    status:'connected', lastSync:'Live',        type:'Communication' },
  { id:'esign',   name:'eMudhra eSign',        desc:'Digital signature integration for document authentication',   status:'error',     lastSync:'Failed',      type:'PKI' },
  { id:'bhuvan',  name:'ISRO Bhuvan GIS',     desc:'Satellite imagery and geospatial analytics from ISRO',        status:'connected', lastSync:'12 hours ago',type:'Geospatial' },
  { id:'gstin',   name:'GSTN Tax Registry',   desc:'Cross-check land tax records against GST registration data',  status:'disconnected',lastSync:'Not configured',type:'Tax' },
];

const STATUS_CONFIG = {
  connected:    { icon:<CheckCircle size={13}/>, label:'Connected',    color:'var(--color-success-600)', bg:'var(--color-success-50)', border:'var(--color-success-100)' },
  warning:      { icon:<AlertTriangle size={13}/>, label:'Degraded',   color:'var(--color-warning-600)', bg:'var(--color-warning-50)', border:'var(--color-warning-100)' },
  error:        { icon:<XCircle size={13}/>, label:'Error',            color:'var(--color-error-600)',   bg:'var(--color-error-50)',   border:'var(--color-error-100)' },
  disconnected: { icon:<XCircle size={13}/>, label:'Not Configured',   color:'var(--text-tertiary)',      bg:'var(--color-slate-75)',   border:'var(--border-default)' },
} as const;

export function IntegrationsPage() {
  const statusCounts = INTEGRATIONS.reduce((a, i) => { a[i.status] = (a[i.status]||0)+1; return a; }, {} as Record<string,number>);

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">Integrations</div>
          <div className="page-hdr__sub">External service connections and government API gateways</div>
        </div>
      </div>

      {/* Status summary */}
      <div style={{ display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'var(--space-4)',marginBottom:'var(--space-5)' }}>
        {[['connected','Connected','var(--color-success-500)'],['warning','Degraded','var(--color-warning-500)'],['error','Error','var(--color-error-500)'],['disconnected','Not Configured','var(--text-tertiary)']].map(([k,l,c])=>(
          <div key={k} className="kpi">
            <div className="kpi__accent" style={{background:c as string}}/>
            <div className="kpi__value">{statusCounts[k as string]??0}</div>
            <div className="kpi__label">{l}</div>
          </div>
        ))}
      </div>

      <div style={{ display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--space-4)' }}>
        {INTEGRATIONS.map(intg => {
          const sc = STATUS_CONFIG[intg.status as keyof typeof STATUS_CONFIG];
          return (
            <div key={intg.id} className="card">
              <div className="card__hdr">
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex',alignItems:'center',gap:8,marginBottom:3 }}>
                    <div className="card__title">{intg.name}</div>
                    <span style={{ padding:'1px 6px',borderRadius:'var(--radius-full)',fontSize:10,fontWeight:600,background:'var(--color-slate-100)',color:'var(--text-secondary)' }}>{intg.type}</span>
                  </div>
                  <div className="card__sub">{intg.desc}</div>
                </div>
                <span style={{ display:'flex',alignItems:'center',gap:5,padding:'4px 10px',borderRadius:'var(--radius-full)',fontSize:11,fontWeight:600,background:sc.bg,color:sc.color,border:`1px solid ${sc.border}`,whiteSpace:'nowrap' }}>
                  {sc.icon} {sc.label}
                </span>
              </div>
              <div className="card__body" style={{ padding:'var(--space-3) var(--space-5)' }}>
                <div style={{ display:'flex',justifyContent:'space-between',alignItems:'center' }}>
                  <span style={{ fontSize:'var(--text-xs)',color:'var(--text-secondary)' }}>Last sync: <strong>{intg.lastSync}</strong></span>
                  <div style={{ display:'flex',gap:'var(--space-2)' }}>
                    <button className="btn btn--ghost btn--xs">Configure</button>
                    <button className="btn btn--ghost btn--xs"><ExternalLink size={11}/></button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
