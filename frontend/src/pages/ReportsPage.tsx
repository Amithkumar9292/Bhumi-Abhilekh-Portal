import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  TrendingUp, MapPin, FileText, AlertTriangle, CheckCircle, Clock,
  Download, RefreshCw, Upload,
} from 'lucide-react';
import { useTranslation } from '../i18n/useTranslation';
import { analyticsApi, type KpiSnapshot } from '../api/analytics';
import { describeError } from '../api/documents';
import { LAND_USE_LABELS, STATUS_LABELS } from '../utils/formatters';

/**
 * Reports — computed from the live database.
 *
 * Every figure on this page used to be a hardcoded constant, so the report
 * described a system nobody had uploaded anything into. Each panel now reads the
 * aggregate the API computed over the same rows the intake pipeline writes, and
 * an empty system reports zeros rather than invented numbers.
 */

const STATUS_COLORS: Record<string, string> = {
  VERIFIED: '#10B981', PENDING: '#F59E0B', UNDER_REVIEW: '#3B82F6',
  REJECTED: '#EF4444', ARCHIVED: '#6B7280',
};

const SEVERITY_COLORS: Record<string, string> = {
  HIGH: '#EF4444', MEDIUM: '#F59E0B', LOW: '#10B981',
};

const LAND_USE_COLORS = ['#10B981', '#3B82F6', '#F59E0B', '#059669', '#6366F1', '#6B7280', '#8B5CF6', '#EC4899'];

const ANOMALY_LABELS: Record<string, string> = {
  DUPLICATE_RECORD: 'Duplicate Record',
  AREA_MISMATCH: 'Area Mismatch',
  OWNER_CONFLICT: 'Owner Conflict',
  BOUNDARY_CONFLICT: 'Boundary Conflict',
  SURVEY_FORMAT_ERROR: 'Survey Format Error',
  MISSING_REQUIRED: 'Missing Required Field',
  LOW_CONFIDENCE_FIELD: 'Low Confidence Field',
};

const DOC_STATUS_LABELS: Record<string, string> = {
  UPLOADED: 'Uploaded',
  PROCESSING: 'Processing',
  VALIDATED: 'Validated',
  REJECTED: 'Rejected',
};

function humanize(value: string): string {
  return value.replace(/_/g, ' ').toLowerCase().replace(/^\w/, c => c.toUpperCase());
}

// ── Chart components (pure SVG) ───────────────────────────────────────────────

function HorizontalBar({ label, value, max, color, suffix = '' }: {
  label: string; value: number; max: number; color: string; suffix?: string;
}) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, fontSize: 'var(--text-xs)', fontWeight: 500 }}>
        <span style={{ color: 'var(--text-primary)', maxWidth: 180 }} className="truncate">{label}</span>
        <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{value.toLocaleString('en-IN')}{suffix}</span>
      </div>
      <div style={{ height: 6, background: 'var(--color-slate-100)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 3, transition: 'width 0.6s ease' }} />
      </div>
    </div>
  );
}

interface DonutSlice { label: string; value: number; pct: number; color: string; path: string }

function DonutChart({ data }: { data: Array<{ label: string; value: number; color: string }> }) {
  const cx = 80, cy = 80, r = 60, inner = 38;
  const total = data.reduce((a, b) => a + b.value, 0);
  if (total === 0) {
    return <div className="empty"><div className="empty__desc">No records yet</div></div>;
  }

  let currentAngle = -90;
  const slices: DonutSlice[] = data.map(d => {
    const angle = (d.value / total) * 360;
    const startAngle = currentAngle;
    currentAngle += angle;
    const endAngle = currentAngle;
    const start = polarToXY(cx, cy, r, startAngle);
    const end = polarToXY(cx, cy, r, endAngle);
    const large = angle > 180 ? 1 : 0;
    const startIn = polarToXY(cx, cy, inner, startAngle);
    const endIn = polarToXY(cx, cy, inner, endAngle);
    const path = `M${start.x} ${start.y} A${r} ${r} 0 ${large} 1 ${end.x} ${end.y} L${endIn.x} ${endIn.y} A${inner} ${inner} 0 ${large} 0 ${startIn.x} ${startIn.y} Z`;
    return { label: d.label, value: d.value, pct: (d.value / total) * 100, color: d.color, path };
  });

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-5)' }}>
      <svg width={160} height={160} style={{ flexShrink: 0 }}>
        {slices.map((s, i) => (
          <path key={i} d={s.path} fill={s.color} stroke="white" strokeWidth={2}>
            <title>{s.label}: {s.value}</title>
          </path>
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize={18} fontWeight={700} fill="var(--text-primary)">{total.toLocaleString('en-IN')}</text>
        <text x={cx} y={cy + 12} textAnchor="middle" fontSize={9} fill="var(--text-tertiary)">TOTAL</text>
      </svg>
      <div style={{ flex: 1 }}>
        {slices.map(s => (
          <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <div style={{ width: 8, height: 8, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            <span style={{ fontSize: 'var(--text-xs)', flex: 1 }}>{s.label}</span>
            <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-secondary)' }}>{s.value}</span>
            <span style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>{s.pct.toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function polarToXY(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

interface ThroughputPoint { label: string; total: number; completed: number; failed: number }

function ThroughputChart({ data }: { data: ThroughputPoint[] }) {
  const W = 620, H = 120, pad = { t: 10, b: 20, l: 4, r: 4 };
  const inner = { w: W - pad.l - pad.r, h: H - pad.t - pad.b };

  if (data.length === 0) {
    return <div className="empty" style={{ padding: 'var(--space-5)' }}><div className="empty__desc">No processing jobs in the last 30 days</div></div>;
  }

  const max = Math.max(...data.map(d => d.total), 1);
  const gap = inner.w / data.length;
  const barW = Math.max(1, Math.floor(gap * 0.7));

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ display: 'block' }}>
      {data.map((d, i) => {
        const x = pad.l + i * gap + (gap - barW) / 2;
        const bh = Math.round((d.completed / max) * inner.h);
        const fh = Math.round((d.failed / max) * inner.h);
        const y = pad.t + inner.h;
        return (
          <g key={i}>
            <rect x={x} y={y - bh - fh} width={barW} height={fh} fill="#EF4444" rx={1}>
              <title>{d.label}: {d.failed} failed</title>
            </rect>
            <rect x={x} y={y - bh} width={barW} height={bh} fill="#10B981" rx={1}>
              <title>{d.label}: {d.completed} completed</title>
            </rect>
            {i % 5 === 0 && (
              <text x={x + barW / 2} y={H - 3} textAnchor="middle" fontSize={8} fill="var(--text-tertiary)">{d.label}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function PassFailBar({ label, rate, pass, fail }: {
  label: string; rate: number; pass: number; fail: number;
}) {
  const pct = Math.max(0, Math.min(100, rate));
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3, gap: 8 }}>
        <span style={{ fontSize: 11, fontWeight: 500, color: 'var(--text-primary)' }} className="truncate">{label}</span>
        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap', color: pct >= 90 ? 'var(--color-success-600)' : 'var(--color-warning-600)' }}>
          {pct.toFixed(1)}% · {pass}/{pass + fail}
        </span>
      </div>
      <div style={{ height: 6, background: 'var(--color-slate-100)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ display: 'flex', height: '100%' }}>
          <div style={{ width: `${pct}%`, background: 'var(--color-success-500)', transition: 'width 0.6s' }} />
          <div style={{ flex: 1, background: 'var(--color-error-200)' }} />
        </div>
      </div>
    </div>
  );
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KPICard({ title, value, sub, icon: Icon, accent }: {
  title: string; value: string | number; sub?: string;
  icon: React.ElementType; accent: string;
}) {
  return (
    <div className="kpi">
      <div className="kpi__accent" style={{ background: accent }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div className="kpi__value">{typeof value === 'number' ? value.toLocaleString('en-IN') : value}</div>
          <div className="kpi__label">{title}</div>
          {sub && <div style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{sub}</div>}
        </div>
        <div style={{ width: 32, height: 32, borderRadius: 8, background: `${accent}18`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Icon size={16} color={accent} />
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

type Tab = 'overview' | 'district' | 'state' | 'validation' | 'anomalies' | 'uploads';

const TABS: Array<[Tab, string]> = [
  ['overview', 'Overview'],
  ['uploads', 'Uploads'],
  ['district', 'By District'],
  ['state', 'By State'],
  ['validation', 'Validation Stats'],
  ['anomalies', 'Anomaly Trends'],
];

export function ReportsPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [kpis, setKpis] = useState<KpiSnapshot | null>(null);
  const [byStatus, setByStatus] = useState<Array<{ status: string; count: number }>>([]);
  const [byDistrict, setByDistrict] = useState<Array<{ district: string; state: string; count: number; total_area_ha: number }>>([]);
  const [byState, setByState] = useState<Array<{ state: string; count: number; verified: number; total_area_ha: number }>>([]);
  const [byLandUse, setByLandUse] = useState<Array<{ land_use: string; count: number; total_area_ha: number }>>([]);
  const [throughput, setThroughput] = useState<Array<{ date: string | null; total: number; completed: number; failed: number }>>([]);
  const [areaBuckets, setAreaBuckets] = useState<Array<{ range: string; count: number }>>([]);
  const [anomalyTrends, setAnomalyTrends] = useState<Array<{ type: string; severity: string; count: number }>>([]);
  const [docSummary, setDocSummary] = useState<{ by_status: Array<{ status: string; count: number }>; by_type: Array<{ document_type: string; count: number }>; records_from_upload: number; records_with_anomalies: number } | null>(null);
  const [validation, setValidation] = useState<Array<{ field_name: string; total: number; accepted: number; rejected: number; pass_rate_pct: number; needs_review: number }>>([]);
  const [accuracy, setAccuracy] = useState<{ data: Array<{ field_name: string; field_display: string; samples: number; found_rate_pct: number; avg_confidence_pct: number }>; overall_confidence_pct: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [
        k, status, district, state, landUse, jobs, area, anomalies, docs, health, acc,
      ] = await Promise.all([
        analyticsApi.getKpis(),
        analyticsApi.getRecordsByStatus(),
        analyticsApi.getRecordsByDistrict(10),
        analyticsApi.getRecordsByState(10),
        analyticsApi.getRecordsByLandUse(),
        analyticsApi.getProcessingThroughput(30),
        analyticsApi.getAreaDistribution(),
        analyticsApi.getAnomalyTrends(),
        analyticsApi.getDocumentsSummary(),
        analyticsApi.getValidationHealth(),
        analyticsApi.getFieldAccuracy(),
      ]);
      setKpis(k);
      setByStatus(status);
      setByDistrict(district);
      setByState(state);
      setByLandUse(landUse);
      setThroughput(jobs);
      setAreaBuckets(area);
      setAnomalyTrends(anomalies);
      setDocSummary(docs);
      setValidation(health);
      setAccuracy(acc);
      setError('');
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const statusData = useMemo(
    () => byStatus.map(s => ({
      label: STATUS_LABELS[s.status] ?? humanize(s.status),
      value: s.count,
      color: STATUS_COLORS[s.status] ?? '#6B7280',
    })),
    [byStatus],
  );

  const throughputPoints = useMemo<ThroughputPoint[]>(
    () => throughput.map(d => ({
      label: d.date
        ? new Date(d.date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })
        : '',
      total: d.total,
      completed: d.completed,
      failed: d.failed,
    })),
    [throughput],
  );

  const anomalyTotal = anomalyTrends.reduce((a, b) => a + b.count, 0);
  const openAnomalies = kpis?.anomalies.open ?? 0;
  const resolutionRate = anomalyTotal > 0
    ? ((anomalyTotal - openAnomalies) / anomalyTotal) * 100
    : 0;

  if (loading && !kpis) {
    return (
      <div className="anim-fade-up" style={{ display: 'flex', justifyContent: 'center', padding: 'var(--space-10)' }}>
        <span className="spinner"/>
      </div>
    );
  }

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">{t('analytics.title')}</div>
          <div className="page-hdr__sub">
            Live metrics computed from uploaded documents, extracted fields and detected anomalies
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button className="btn btn--secondary btn--sm" onClick={() => { void load(); }}>
            <RefreshCw size={13} className={loading ? 'spin' : ''}/> Refresh
          </button>
          <button className="btn btn--secondary btn--md" onClick={() => window.print()}>
            <Download size={13}/> Export PDF
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          {error}
        </div>
      )}

      <div className="demo-banner">
        <AlertTriangle size={13}/>
        <span>{t('sys.nonLegalBinding')}</span>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 'var(--space-3)', marginBottom: 'var(--space-5)' }}>
        <KPICard
          title="Total Records" value={kpis?.records.total ?? 0}
          sub={`${kpis?.documents.records_from_upload ?? 0} from uploads`}
          icon={FileText} accent="#3B82F6"
        />
        <KPICard
          title="Verified" value={kpis?.records.verified ?? 0}
          sub={`${kpis?.records.verification_rate_pct ?? 0}% rate`}
          icon={CheckCircle} accent="#10B981"
        />
        <KPICard
          title="Area Digitized" value={`${(kpis?.area.total_hectares ?? 0).toFixed(0)} ha`}
          sub={`${byDistrict.length} districts`}
          icon={MapPin} accent="#6366F1"
        />
        <KPICard
          title="Jobs Processed" value={kpis?.pipeline.total_jobs ?? 0}
          sub={`${kpis?.pipeline.success_rate_pct ?? 0}% success`}
          icon={TrendingUp} accent="#F59E0B"
        />
        <KPICard
          title="Open Anomalies" value={openAnomalies}
          sub={`${anomalyTotal} detected in total`}
          icon={AlertTriangle} accent="#EF4444"
        />
        <KPICard
          title="Pending Review" value={kpis?.pipeline.pending_review ?? 0}
          sub={`${kpis?.records.under_review ?? 0} records awaiting officer`}
          icon={Clock} accent="#8B5CF6"
        />
      </div>

      {/* Tabs */}
      <div className="tabs" style={{ marginBottom: 'var(--space-4)' }}>
        {TABS.map(([id, label]) => (
          <button key={id} className={`tab-btn${activeTab === id ? ' active' : ''}`} onClick={() => setActiveTab(id)}>
            {label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && (
        <div className="anim-fade-in" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">{t('analytics.recordsByStatus')}</div>
            </div>
            <div className="card__body">
              <DonutChart data={statusData} />
            </div>
          </div>

          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Land Use Classification</div>
            </div>
            <div className="card__body">
              {byLandUse.length === 0
                ? <div className="empty" style={{ padding: 'var(--space-5)' }}><div className="empty__desc">No records yet</div></div>
                : byLandUse.map((d, i) => (
                  <HorizontalBar
                    key={d.land_use}
                    label={LAND_USE_LABELS[d.land_use] ?? humanize(d.land_use)}
                    value={d.count}
                    max={Math.max(...byLandUse.map(x => x.count))}
                    color={LAND_USE_COLORS[i % LAND_USE_COLORS.length]}
                    suffix=" records"
                  />
                ))}
            </div>
          </div>

          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card__hdr">
              <div className="card__title">{t('analytics.processingThroughput')}</div>
              <div style={{ display: 'flex', gap: 'var(--space-3)', fontSize: 11 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 8, height: 8, background: '#10B981', borderRadius: 1, display: 'inline-block' }}/> Completed</span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><span style={{ width: 8, height: 8, background: '#EF4444', borderRadius: 1, display: 'inline-block' }}/> Failed</span>
              </div>
            </div>
            <div className="card__body" style={{ paddingTop: 0 }}>
              <ThroughputChart data={throughputPoints} />
            </div>
          </div>

          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card__hdr">
              <div className="card__title">{t('analytics.areaDistribution')}</div>
            </div>
            <div className="card__body" style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(1, areaBuckets.length)}, 1fr)`, gap: 'var(--space-2)', alignItems: 'flex-end', height: 120 }}>
              {areaBuckets.map(d => {
                const max = Math.max(...areaBuckets.map(x => x.count), 1);
                const h = Math.max(4, Math.round((d.count / max) * 90));
                return (
                  <div key={d.range} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
                    <span style={{ fontSize: 9, color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{d.count}</span>
                    <div style={{ height: h, width: '100%', background: 'var(--color-navy-700)', borderRadius: '2px 2px 0 0', transition: 'height 0.6s' }} title={`${d.range}: ${d.count} records`} />
                    <span style={{ fontSize: 8, color: 'var(--text-tertiary)', textAlign: 'center', lineHeight: 1.2 }}>{d.range}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Uploads */}
      {activeTab === 'uploads' && (
        <div className="anim-fade-in" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Documents by Pipeline Status</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{kpis?.documents.total ?? 0} uploaded</div>
            </div>
            <div className="card__body">
              {docSummary && docSummary.by_status.length > 0 ? (
                docSummary.by_status.map(s => (
                  <HorizontalBar
                    key={s.status}
                    label={DOC_STATUS_LABELS[s.status] ?? humanize(s.status)}
                    value={s.count}
                    max={Math.max(...docSummary.by_status.map(x => x.count))}
                    color={s.status === 'VALIDATED' ? '#10B981' : s.status === 'REJECTED' ? '#EF4444' : s.status === 'PROCESSING' ? '#3B82F6' : '#F59E0B'}
                    suffix=" files"
                  />
                ))
              ) : (
                <div className="empty" style={{ padding: 'var(--space-5)' }}>
                  <div className="empty__icon"><Upload size={22}/></div>
                  <div className="empty__title">Nothing uploaded yet</div>
                  <div className="empty__desc">Upload a land record document and it will be counted here once processing starts.</div>
                </div>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Documents by Type</div>
            </div>
            <div className="card__body">
              {docSummary && docSummary.by_type.length > 0 ? (
                docSummary.by_type.map((d, i) => (
                  <HorizontalBar
                    key={d.document_type}
                    label={humanize(d.document_type)}
                    value={d.count}
                    max={Math.max(...docSummary.by_type.map(x => x.count))}
                    color={LAND_USE_COLORS[i % LAND_USE_COLORS.length]}
                    suffix=" files"
                  />
                ))
              ) : (
                <div className="empty" style={{ padding: 'var(--space-5)' }}><div className="empty__desc">No documents to classify</div></div>
              )}
            </div>
          </div>

          <div className="card" style={{ gridColumn: '1 / -1' }}>
            <div className="card__body">
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--space-4)' }}>
                <div className="info-row">
                  <div className="info-row__label">Uploaded (24h)</div>
                  <div className="info-row__value">{kpis?.documents.uploaded_last_24h ?? 0}</div>
                </div>
                <div className="info-row">
                  <div className="info-row__label">Records created from uploads</div>
                  <div className="info-row__value">{docSummary?.records_from_upload ?? 0}</div>
                </div>
                <div className="info-row">
                  <div className="info-row__label">Of those, flagged</div>
                  <div className="info-row__value">{docSummary?.records_with_anomalies ?? 0}</div>
                </div>
                <div className="info-row">
                  <div className="info-row__label">Processing success</div>
                  <div className="info-row__value">{kpis?.pipeline.success_rate_pct ?? 0}%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* District breakdown */}
      {activeTab === 'district' && (
        <div className="card anim-fade-in">
          <div className="card__hdr">
            <div className="card__title">Records by District</div>
            <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Top {byDistrict.length} districts by record count</div>
          </div>
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr><th>District</th><th>State</th><th>Records</th><th>Area (ha)</th><th>Distribution</th></tr>
              </thead>
              <tbody>
                {byDistrict.length === 0 && (
                  <tr><td colSpan={5} style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-tertiary)' }}>No district data yet.</td></tr>
                )}
                {byDistrict.map((d, i) => {
                  const share = kpis?.records.total ? (d.count / kpis.records.total) * 100 : 0;
                  return (
                    <tr key={`${d.state}-${d.district}`}>
                      <td><span style={{ fontWeight: 600 }}>#{i + 1} {d.district}</span></td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{d.state}</td>
                      <td><code style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>{d.count}</code></td>
                      <td><code style={{ fontSize: 12, fontFamily: 'var(--font-mono)' }}>{d.total_area_ha.toFixed(1)}</code></td>
                      <td style={{ width: 180 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ flex: 1, height: 4, background: 'var(--color-slate-100)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${share}%`, background: 'var(--color-navy-700)', borderRadius: 2 }} />
                          </div>
                          <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-tertiary)' }}>{share.toFixed(1)}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* State breakdown */}
      {activeTab === 'state' && (
        <div className="card anim-fade-in">
          <div className="card__hdr">
            <div className="card__title">State-wise Digitization Progress</div>
          </div>
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr><th>State</th><th>Total Records</th><th>Verified</th><th>Verification Rate</th><th>Total Area (ha)</th></tr>
              </thead>
              <tbody>
                {byState.length === 0 && (
                  <tr><td colSpan={5} style={{ padding: 'var(--space-6)', textAlign: 'center', color: 'var(--text-tertiary)' }}>No state data yet.</td></tr>
                )}
                {byState.map(s => {
                  const rate = s.count ? (s.verified / s.count) * 100 : 0;
                  return (
                    <tr key={s.state}>
                      <td style={{ fontWeight: 600 }}>{s.state}</td>
                      <td><code style={{ fontFamily: 'var(--font-mono)' }}>{s.count}</code></td>
                      <td><code style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-success-700)' }}>{s.verified}</code></td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <div style={{ width: 60, height: 4, background: 'var(--color-slate-100)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${rate}%`, background: rate >= 60 ? 'var(--color-success-500)' : 'var(--color-warning-500)', borderRadius: 2 }} />
                          </div>
                          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600, color: rate >= 60 ? 'var(--color-success-700)' : 'var(--color-warning-700)' }}>{rate.toFixed(0)}%</span>
                        </div>
                      </td>
                      <td><code style={{ fontFamily: 'var(--font-mono)' }}>{s.total_area_ha.toFixed(1)}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Validation stats */}
      {activeTab === 'validation' && (
        <div className="anim-fade-in" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)' }}>
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Field Validation Pass Rates</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                {validation.length} fields read from uploads
              </div>
            </div>
            <div className="card__body">
              {validation.length === 0 ? (
                <div className="empty" style={{ padding: 'var(--space-5)' }}>
                  <div className="empty__title">Nothing to validate yet</div>
                  <div className="empty__desc">Rates appear once a document has been processed.</div>
                </div>
              ) : validation.map(v => (
                <PassFailBar
                  key={v.field_name}
                  label={v.field_name.replace(/_/g, ' ')}
                  rate={v.pass_rate_pct}
                  pass={v.accepted}
                  fail={v.rejected}
                />
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Extraction Accuracy by Field</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>
                overall {accuracy?.overall_confidence_pct ?? 0}% confidence
              </div>
            </div>
            <div className="card__body">
              {accuracy && accuracy.data.length > 0 ? (
                <>
                  {accuracy.data.map(a => (
                    <HorizontalBar
                      key={a.field_name}
                      label={a.field_display || a.field_name.replace(/_/g, ' ')}
                      value={a.avg_confidence_pct}
                      max={100}
                      color={a.avg_confidence_pct >= 90 ? '#10B981' : a.avg_confidence_pct >= 70 ? '#F59E0B' : '#EF4444'}
                      suffix="%"
                    />
                  ))}
                  <div style={{ marginTop: 'var(--space-3)', fontSize: 11, color: 'var(--text-tertiary)' }}>
                    A field only appears here once a scan has been read.{' '}
                    {validation.reduce((a, b) => a + b.needs_review, 0)} field reads are still waiting for human review.
                  </div>
                </>
              ) : (
                <div className="empty" style={{ padding: 'var(--space-5)' }}>
                  <div className="empty__title">No extraction data yet</div>
                  <div className="empty__desc">Upload and process a document to populate field accuracy.</div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Anomaly trends */}
      {activeTab === 'anomalies' && (
        <div className="anim-fade-in" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 'var(--space-5)' }}>
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Anomaly Distribution by Type</div>
            </div>
            <div className="card__body">
              {anomalyTrends.length === 0 ? (
                <div className="empty" style={{ padding: 'var(--space-5)' }}>
                  <div className="empty__icon">✅</div>
                  <div className="empty__title">No anomalies detected</div>
                  <div className="empty__desc">Nothing in the processed uploads has tripped a validation rule.</div>
                </div>
              ) : (
                anomalyTrends.map(a => (
                  <HorizontalBar
                    key={`${a.type}-${a.severity}`}
                    label={ANOMALY_LABELS[a.type] ?? humanize(a.type)}
                    value={a.count}
                    max={Math.max(...anomalyTrends.map(x => x.count))}
                    color={SEVERITY_COLORS[a.severity] ?? '#F59E0B'}
                    suffix=" cases"
                  />
                ))
              )}
            </div>
          </div>
          <div className="card">
            <div className="card__hdr"><div className="card__title">By Severity</div></div>
            <div className="card__body">
              {(['HIGH', 'MEDIUM', 'LOW'] as const).map(sev => {
                const count = anomalyTrends.filter(a => a.severity === sev).reduce((a, b) => a + b.count, 0);
                const color = SEVERITY_COLORS[sev];
                return (
                  <div key={sev} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', borderBottom: '1px solid var(--color-slate-75)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ width: 8, height: 8, borderRadius: 2, background: color }} />
                      <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{sev}</span>
                    </div>
                    <code style={{ fontSize: 16, fontFamily: 'var(--font-mono)', fontWeight: 700, color }}>{count}</code>
                  </div>
                );
              })}
              <div style={{ marginTop: 'var(--space-4)', padding: 'var(--space-3)', background: 'var(--color-warning-50)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-warning-100)' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--color-warning-800)', marginBottom: 4 }}>⚠ Resolution Rate</div>
                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-warning-700)' }}>
                  {anomalyTotal === 0
                    ? 'No anomaly has been raised yet.'
                    : `${resolutionRate.toFixed(0)}% of detected anomalies are resolved; ${openAnomalies} still need a verifier.`}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
