import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  FileText, Users, CheckCircle, Clock, AlertTriangle, XCircle,
  TrendingUp, ArrowRight, Activity,
} from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { getMockListItems, getMockAnomalies, getMockAuditEvents, MOCK_DASHBOARD_STATS } from '../mock/mockData';
import { formatRelative, STATUS_LABELS, getIntlLocale } from '../utils/formatters';
import { useTranslation } from '../i18n/useTranslation';

function KPICard({ label, value, icon, color, accent, trend }:
  { label:string; value:number|string; icon:React.ReactNode; color:string; accent:string; trend?:string }) {
  return (
    <div className="kpi">
      <div className="kpi__accent" style={{background:accent}}/>
      <div className="kpi__icon-wrap" style={{background:color}}>
        {icon}
      </div>
      <div className="kpi__value">{value.toLocaleString()}</div>
      <div className="kpi__label">{label}</div>
      {trend && <div className="kpi__trend"><TrendingUp size={11}/>{trend}</div>}
    </div>
  );
}

export function DashboardPage() {
  const { user } = useAuthStore();
  const { t, lang } = useTranslation();
  const stats = MOCK_DASHBOARD_STATS;
  const recentRecords = getMockListItems().slice(0, 8);
  const recentAudit   = getMockAuditEvents().slice(0, 6);
  const anomalies     = getMockAnomalies().filter(a => !a.resolved).slice(0, 4);

  return (
    <div className="anim-fade-up">
      <div className="demo-banner">
        <AlertTriangle size={13}/>
        <span>{t('sys.nonLegalBinding')}</span>
      </div>

      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">
            Good {new Date().getHours() < 12 ? 'Morning' : new Date().getHours() < 17 ? 'Afternoon' : 'Evening'}, {user?.full_name?.split(' ')[0]} 👋
          </div>
          <div className="page-hdr__sub">
            {new Date().toLocaleDateString(getIntlLocale(lang), { weekday:'long', day:'numeric', month:'long', year:'numeric' })}
          </div>
        </div>
        <Link to="/intake" className="btn btn--primary btn--md">
          <FileText size={14}/> New Intake
        </Link>
      </div>

      {/* KPIs */}
      <div className="kpi-grid" style={{marginBottom:'var(--space-6)'}}>
        <KPICard label={t('dash.totalRecords')}  value={stats.records.total}       icon={<FileText size={16} color="#003580"/>}     color="#EFF6FF" accent="#003580" trend="+12 this month" />
        <KPICard label={t('dash.pendingReview')} value={stats.records.pending}     icon={<Clock size={16} color="#92400E"/>}        color="#FEF3C7" accent="#F29900" />
        <KPICard label={t('status.underReview')} value={stats.records.under_review}icon={<Activity size={16} color="#1D4ED8"/>}    color="#EFF6FF" accent="#2563EB" />
        <KPICard label={t('dash.verified')}      value={stats.records.verified}    icon={<CheckCircle size={16} color="#065F46"/>} color="#ECFDF5" accent="#10A65A" trend="84%" />
        <KPICard label={t('status.rejected')}    value={stats.records.rejected}    icon={<XCircle size={16} color="#991B1B"/>}    color="#FEF2F2" accent="#E53E3E" />
        <KPICard label={t('dash.docsProcessed')} value={stats.documents.total}     icon={<FileText size={16} color="#5B21B6"/>}    color="#F5F3FF" accent="#7C3AED" />
        <KPICard label={t('users.active')}       value={stats.users.total}         icon={<Users size={16} color="#065F46"/>}       color="#ECFDF5" accent="#059669" />
        <KPICard label={t('dash.anomalies')}     value={anomalies.length}          icon={<AlertTriangle size={16} color="#B45309"/>} color="#FEF3C7" accent="#D97706" />
      </div>

      {/* Two-column layout */}
      <div style={{display:'grid', gridTemplateColumns:'1fr 360px', gap:'var(--space-5)', alignItems:'start'}}>
        {/* Recent Records */}
        <div className="card">
          <div className="card__hdr">
            <div>
              <div className="card__title">Recent Land Records</div>
              <div className="card__sub">Latest submissions across all districts</div>
            </div>
            <Link to="/land-records" className="btn btn--ghost btn--sm">View all <ArrowRight size={12}/></Link>
          </div>
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Khasra No.</th>
                  <th>Owner</th>
                  <th>District</th>
                  <th>Area (ha)</th>
                  <th>Status</th>
                  <th>Submitted</th>
                </tr>
              </thead>
              <tbody>
                {recentRecords.map(r => (
                  <tr key={r.id}>
                    <td><Link to={`/land-records/${r.id}`} style={{color:'var(--color-navy-700)',fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)'}}>{r.khasra_number}</Link></td>
                    <td style={{fontWeight:500}}>{r.owner_name}</td>
                    <td style={{color:'var(--text-secondary)',fontSize:'var(--text-xs)'}}>{r.district}</td>
                    <td style={{fontFamily:'var(--font-mono)',fontSize:'var(--text-xs)'}}>{r.area_hectares}</td>
                    <td><span className={`badge badge--${r.status}`}>{STATUS_LABELS[r.status]}</span></td>
                    <td style={{color:'var(--text-tertiary)',fontSize:'var(--text-xs)'}}>{formatRelative(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right column */}
        <div style={{display:'flex',flexDirection:'column',gap:'var(--space-4)'}}>
          {/* Anomalies */}
          <div className="card">
            <div className="card__hdr">
              <div className="card__title" style={{display:'flex',alignItems:'center',gap:6}}>
                <AlertTriangle size={14} color="var(--color-warning-600)"/> Open Anomalies
              </div>
              <Link to="/anomalies" className="btn btn--ghost btn--xs">View all</Link>
            </div>
            <div style={{padding:'var(--space-3) var(--space-4)',display:'flex',flexDirection:'column',gap:'var(--space-2)'}}>
              {anomalies.map(a => (
                <div key={a.id} style={{padding:'8px 10px',background:'var(--color-slate-50)',borderRadius:'var(--radius-lg)',border:'1px solid var(--border-default)'}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:3}}>
                    <span style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--color-navy-700)'}}>{a.khasra_number}</span>
                    <span className={`badge badge--${a.severity}`}>{a.severity}</span>
                  </div>
                  <div style={{fontSize:11,color:'var(--text-secondary)'}}>{a.description}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Audit activity */}
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Recent Activity</div>
              <Link to="/audit" className="btn btn--ghost btn--xs">View all</Link>
            </div>
            <div style={{padding:'var(--space-3) var(--space-4)'}}>
              {recentAudit.map(e => (
                <div key={e.id} style={{display:'flex',alignItems:'flex-start',gap:8,paddingBottom:10,marginBottom:10,borderBottom:'1px solid var(--color-slate-75)'}}>
                  <div style={{width:6,height:6,borderRadius:'50%',background:e.status==='SUCCESS'?'var(--color-success-500)':'var(--color-error-500)',marginTop:6,flexShrink:0}}/>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontSize:'var(--text-xs)',fontWeight:600,color:'var(--text-primary)'}}>{e.action.replace(/_/g,' ')}</div>
                    <div style={{fontSize:11,color:'var(--text-secondary)'}}>{e.actor}</div>
                  </div>
                  <div style={{fontSize:10,color:'var(--text-tertiary)',whiteSpace:'nowrap'}}>{formatRelative(e.timestamp)}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
