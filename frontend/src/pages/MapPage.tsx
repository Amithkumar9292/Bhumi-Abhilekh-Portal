import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { MapPin, Layers, ZoomIn, ZoomOut, Maximize, RefreshCw, Upload } from 'lucide-react';
import { gisApi, type GisFeature } from '../api/gis';
import { describeError } from '../api/documents';

// ── Projection ───────────────────────────────────────────────────────────────
// A real tile server (Leaflet/MapLibre) is out of scope here, so parcels are
// drawn into an SVG canvas with a plain equirectangular projection. The point of
// this page is that a freshly uploaded scan shows up on the map with the
// position the processing pipeline derived for it, which needs real coordinates
// -- not a decorative grid of made-up rectangles.

const CANVAS = { w: 1000, h: 620, padding: 48 };

const STATUS_COLORS: Record<string, string> = {
  PENDING: '#F59E0B', UNDER_REVIEW: '#3B82F6',
  VERIFIED: '#10B981', REJECTED: '#EF4444', ARCHIVED: '#94A3B8',
};

const UPLOAD_COLOR = '#7C3AED';

type Projection = {
  project: (lat: number, lng: number) => [number, number];
  scale: number;
};

function buildProjection(points: Array<{ lat: number; lng: number }>): Projection {
  let latMin = Infinity, latMax = -Infinity, lngMin = Infinity, lngMax = -Infinity;
  for (const p of points) {
    latMin = Math.min(latMin, p.lat);
    latMax = Math.max(latMax, p.lat);
    lngMin = Math.min(lngMin, p.lng);
    lngMax = Math.max(lngMax, p.lng);
  }
  if (!Number.isFinite(latMin)) {
    latMin = 20; latMax = 28; lngMin = 73; lngMax = 84;
  }
  // A single parcel would otherwise divide by zero and cover the canvas.
  const MIN_SPAN = 0.05;
  if (latMax - latMin < MIN_SPAN) {
    const mid = (latMax + latMin) / 2;
    latMin = mid - MIN_SPAN / 2; latMax = mid + MIN_SPAN / 2;
  }
  if (lngMax - lngMin < MIN_SPAN) {
    const mid = (lngMax + lngMin) / 2;
    lngMin = mid - MIN_SPAN / 2; lngMax = mid + MIN_SPAN / 2;
  }

  // Longitude degrees shrink towards the poles; without this correction India
  // would be drawn roughly 30% too wide for its height.
  const midLat = (latMin + latMax) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180);
  const worldW = (lngMax - lngMin) * kx;
  const worldH = latMax - latMin;

  const usableW = CANVAS.w - CANVAS.padding * 2;
  const usableH = CANVAS.h - CANVAS.padding * 2;
  const scale = Math.min(usableW / (worldW || 1), usableH / (worldH || 1));
  const offX = (CANVAS.w - worldW * scale) / 2;
  const offY = (CANVAS.h - worldH * scale) / 2;

  return {
    scale,
    project: (lat: number, lng: number) => [
      offX + (lng - lngMin) * kx * scale,
      offY + (latMax - lat) * scale,
    ],
  };
}

/** Centroid of a feature, falling back to the first polygon vertex. */
function centroidOf(feature: GisFeature): { lat: number; lng: number } | null {
  const p = feature.properties;
  if (p.latitude != null && p.longitude != null) {
    return { lat: p.latitude, lng: p.longitude };
  }
  const geom = feature.geometry;
  if (geom?.type === 'Point' && Array.isArray(geom.coordinates)) {
    const [lng, lat] = geom.coordinates as number[];
    return { lat, lng };
  }
  if (geom?.type === 'Polygon' && Array.isArray(geom.coordinates)) {
    const ring = (geom.coordinates as number[][][])[0];
    const first = ring?.[0];
    if (first) return { lat: first[1], lng: first[0] };
  }
  return null;
}

function polygonPoints(feature: GisFeature, project: Projection['project']): string {
  const geom = feature.geometry;
  if (geom?.type !== 'Polygon' || !Array.isArray(geom.coordinates)) return '';
  const ring = (geom.coordinates as number[][][])[0] ?? [];
  return ring
    .map(([lng, lat]) => project(lat, lng).map(n => n.toFixed(1)).join(','))
    .join(' ');
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function MapPage() {
  const [features, setFeatures] = useState<GisFeature[]>([]);
  const [fromUpload, setFromUpload] = useState(0);
  const [disclaimer, setDisclaimer] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [onlyUploads, setOnlyUploads] = useState(false);
  const [zoom, setZoom] = useState(1);
  const mapRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await gisApi.listRecords({ limit: 500 });
      setFeatures(res.features);
      setFromUpload(res.from_upload);
      setDisclaimer(res.disclaimer);
      setError('');
    } catch (err) {
      setError(describeError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const visible = useMemo(
    () => (onlyUploads ? features.filter(f => f.properties.from_upload) : features),
    [features, onlyUploads],
  );

  const projection = useMemo(
    () => buildProjection(
      visible
        .map(centroidOf)
        .filter((c): c is { lat: number; lng: number } => c !== null),
    ),
    [visible],
  );

  const sel = visible.find(f => f.properties.id === selected) ?? null;

  const zoomBy = (factor: number) => {
    setZoom(z => Math.min(8, Math.max(1, Number((z * factor).toFixed(2)))));
  };

  const fullscreen = () => {
    const el = mapRef.current;
    if (el?.requestFullscreen) void el.requestFullscreen();
  };

  return (
    <div className="anim-fade-up">
      <div className="page-hdr">
        <div>
          <div className="page-hdr__title">GIS / Cadastral Map</div>
          <div className="page-hdr__sub">
            Every georeferenced parcel · {fromUpload} from uploaded document{fromUpload === 1 ? '' : 's'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
          <button
            className={`btn btn--${onlyUploads ? 'primary' : 'secondary'} btn--sm`}
            onClick={() => setOnlyUploads(v => !v)}
            disabled={fromUpload === 0}
            title={fromUpload === 0 ? 'No uploaded document has been georeferenced yet' : undefined}
          >
            <Upload size={13}/> Uploaded only
          </button>
          <button className="btn btn--secondary btn--sm" onClick={() => { void load(); }}>
            <RefreshCw size={13} className={loading ? 'spin' : ''}/> Refresh
          </button>
          <button className="btn btn--secondary btn--sm" onClick={fullscreen}>
            <Maximize size={13}/> Full Screen
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert--error" style={{ marginBottom: 'var(--space-4)' }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 'var(--space-5)', alignItems: 'start' }}>
        {/* Map */}
        <div ref={mapRef} className="map-placeholder" style={{ height: 520, position: 'relative' }}>
          <div className="map-grid"/>
          <svg
            width="100%" height="100%"
            viewBox={`0 0 ${CANVAS.w} ${CANVAS.h}`}
            preserveAspectRatio="xMidYMid meet"
            style={{ position: 'absolute', inset: 0 }}
          >
            <g
              transform={`translate(${CANVAS.w / 2},${CANVAS.h / 2}) scale(${zoom}) translate(${-CANVAS.w / 2},${-CANVAS.h / 2})`}
            >
              {visible.map(f => {
                const p = f.properties;
                const isSel = p.id === selected;
                const centroid = centroidOf(f);
                const points = polygonPoints(f, projection.project);
                const [cx, cy] = centroid ? projection.project(centroid.lat, centroid.lng) : [0, 0];
                const color = STATUS_COLORS[p.status] ?? '#94A3B8';
                const label = p.khasra_number.replace(/^[A-Z]+-/, '');

                return (
                  <g
                    key={p.id}
                    onClick={() => setSelected(isSel ? null : p.id)}
                    style={{ cursor: 'pointer' }}
                  >
                    {points ? (
                      <polygon
                        points={points}
                        fill={p.from_upload ? UPLOAD_COLOR : color}
                        fillOpacity={isSel ? 0.75 : 0.35}
                        stroke={isSel ? '#1E3A5F' : 'rgba(255,255,255,0.85)'}
                        strokeWidth={isSel ? 3 : 1.2}
                        strokeDasharray={p.from_upload && !isSel ? '6 3' : undefined}
                      />
                    ) : (
                      <circle
                        cx={cx} cy={cy} r={isSel ? 9 : 6}
                        fill={p.from_upload ? UPLOAD_COLOR : color}
                        fillOpacity={0.8}
                        stroke="rgba(255,255,255,0.9)"
                        strokeWidth={1.2}
                      />
                    )}
                    <text
                      x={cx} y={cy + 4}
                      textAnchor="middle" fontSize={11} fill="white" fontWeight={700} fontFamily="monospace"
                      style={{ pointerEvents: 'none' }}
                    >
                      {label}
                    </text>
                    <title>
                      {`${p.khasra_number} — ${p.village}, ${p.district} (${p.status})`}
                    </title>
                  </g>
                );
              })}
            </g>
          </svg>

          {/* Map controls */}
          <div style={{ position: 'absolute', top: 12, left: 12, display: 'flex', flexDirection: 'column', gap: 4 }}>
            <button
              onClick={() => zoomBy(1.4)} disabled={zoom >= 8}
              style={{ width: 32, height: 32, background: 'white', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: 'var(--shadow-sm)' }}
            >
              <ZoomIn size={14}/>
            </button>
            <button
              onClick={() => zoomBy(1 / 1.4)} disabled={zoom <= 1}
              style={{ width: 32, height: 32, background: 'white', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: 'var(--shadow-sm)' }}
            >
              <ZoomOut size={14}/>
            </button>
            <button
              onClick={() => setZoom(1)} disabled={zoom === 1}
              title="Reset zoom"
              style={{ width: 32, height: 32, background: 'white', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', boxShadow: 'var(--shadow-sm)', fontSize: 10, fontWeight: 700 }}
            >
              {Math.round(zoom * 100)}%
            </button>
          </div>

          {/* Legend */}
          <div style={{ position: 'absolute', bottom: 16, left: 16, background: 'rgba(255,255,255,0.95)', borderRadius: 'var(--radius-lg)', padding: '10px 14px', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-sm)' }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>Status Legend</div>
            {Object.entries(STATUS_COLORS).map(([s, c]) => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 3 }}>
                <div style={{ width: 12, height: 12, background: c, borderRadius: 2, opacity: 0.7 }}/>
                {s.replace('_', ' ')}
              </div>
            ))}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginTop: 6, paddingTop: 6, borderTop: '1px solid var(--color-slate-75)' }}>
              <div style={{ width: 12, height: 12, background: UPLOAD_COLOR, borderRadius: 2, opacity: 0.7 }}/>
              From uploaded scan
            </div>
          </div>

          <div
            style={{ position: 'absolute', top: 12, right: 12, background: 'rgba(255,255,255,0.9)', borderRadius: 'var(--radius-md)', padding: '6px 10px', fontSize: 10, color: 'var(--text-secondary)', border: '1px solid var(--border-default)', maxWidth: 260, textAlign: 'right' }}
          >
            {disclaimer || '📍 WGS-84 coordinates'}
          </div>

          {loading && features.length === 0 && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.75)' }}>
              <span className="spinner"/>
            </div>
          )}

          {!loading && !error && visible.length === 0 && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div className="empty">
                <div className="empty__icon">🗺</div>
                <div className="empty__title">
                  {onlyUploads ? 'No uploaded document on the map yet' : 'No georeferenced parcels'}
                </div>
                <div className="empty__desc">
                  {onlyUploads
                    ? 'Upload a document and let processing finish — the pipeline places every parcel it reads.'
                    : 'A parcel appears here once it has a centroid. Records created from an upload get one automatically.'}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Side panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {sel ? (
            <div className="card anim-fade-in">
              <div className="card__hdr">
                <div>
                  <div className="card__title">{sel.properties.khasra_number}</div>
                  <div className="card__sub">{sel.properties.village}, {sel.properties.district}</div>
                </div>
                <span className={`badge badge--${sel.properties.status}`}>{sel.properties.status}</span>
              </div>
              <div className="card__body">
                {[
                  ['Owner', sel.properties.owner_name],
                  ['Area', `${sel.properties.area_hectares} ha`],
                  ['Land Use', sel.properties.land_use_type],
                  ['District', sel.properties.district],
                  ['Latitude', sel.properties.latitude?.toFixed(5) ?? '—'],
                  ['Longitude', sel.properties.longitude?.toFixed(5) ?? '—'],
                  ['Position source', sel.properties.source ?? '—'],
                ].map(([l, v]) => (
                  <div className="info-row" key={String(l)}>
                    <div className="info-row__label">{l}</div>
                    <div className="info-row__value">{v}</div>
                  </div>
                ))}

                {sel.properties.from_upload ? (
                  <div style={{ marginTop: 'var(--space-3)', padding: 'var(--space-2) var(--space-3)', background: 'var(--color-info-50)', border: '1px solid var(--color-info-100)', borderRadius: 'var(--radius-md)', fontSize: 11, color: 'var(--color-info-700)' }}>
                    <strong>From upload:</strong>{' '}
                    {sel.properties.document_name ?? 'processed document'}
                  </div>
                ) : (
                  <div style={{ marginTop: 'var(--space-3)', fontSize: 11, color: 'var(--text-tertiary)' }}>
                    <Layers size={11} style={{ verticalAlign: -1 }}/> No uploaded document linked to this parcel yet.
                  </div>
                )}

                <div style={{ marginTop: 'var(--space-4)' }}>
                  <Link to={`/land-records/${sel.properties.id}`} className="btn btn--primary btn--sm" style={{ width: '100%', justifyContent: 'center' }}>
                    <MapPin size={13}/> View Full Record
                  </Link>
                </div>
              </div>
            </div>
          ) : (
            <div className="card">
              <div className="card__body">
                <div className="empty" style={{ padding: 'var(--space-8) var(--space-4)' }}>
                  <div className="empty__icon">🗺</div>
                  <div className="empty__title">Click a parcel</div>
                  <div className="empty__desc">Select a land parcel on the map to view its details</div>
                </div>
              </div>
            </div>
          )}

          {/* Parcel list */}
          <div className="card">
            <div className="card__hdr">
              <div className="card__title">Parcels in View</div>
              <div style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{visible.length}</div>
            </div>
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {visible.map(f => {
                const p = f.properties;
                return (
                  <div
                    key={p.id}
                    onClick={() => setSelected(p.id === selected ? null : p.id)}
                    style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', borderBottom: '1px solid var(--color-slate-75)', cursor: 'pointer', background: p.id === selected ? 'var(--color-navy-50)' : 'transparent', transition: 'background var(--transition-fast)' }}
                  >
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: p.from_upload ? UPLOAD_COLOR : STATUS_COLORS[p.status], flexShrink: 0 }}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 'var(--text-xs)', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--color-navy-700)' }}>{p.khasra_number}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)' }} className="truncate">
                        {p.from_upload && p.document_name ? `📄 ${p.document_name}` : p.owner_name}
                      </div>
                    </div>
                    <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>{p.area_hectares} ha</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
