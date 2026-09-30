/**
 * Mock data layer — works entirely offline without the FastAPI backend.
 * All data is synthetic and non-legally binding.
 */

import type { User } from '../types/auth';
import type { LandRecord, LandRecordListItem, DashboardStats } from '../types/land';

// ── Users ─────────────────────────────────────────────────────
export const MOCK_USERS: Record<string, { user: User; password: string }> = {
  admin: {
    password: 'Admin@1234',
    user: { id: 'u-001', username: 'admin', email: 'admin@bhumi.gov.in', full_name: 'Arjun Sharma', role: 'ADMIN', district_code: null, is_active: true, last_login: new Date(Date.now() - 3600000).toISOString(), created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
  },
  officer_rajesh: {
    password: 'Officer@1234',
    user: { id: 'u-002', username: 'officer_rajesh', email: 'rajesh.kumar@bhumi.gov.in', full_name: 'Rajesh Kumar', role: 'OFFICER', district_code: 'UP-LKO', is_active: true, last_login: new Date(Date.now() - 7200000).toISOString(), created_at: '2024-01-15T00:00:00Z', updated_at: '2024-01-15T00:00:00Z' },
  },
  verifier_priya: {
    password: 'Verifier@1234',
    user: { id: 'u-003', username: 'verifier_priya', email: 'priya.sharma@bhumi.gov.in', full_name: 'Priya Sharma', role: 'VERIFIER', district_code: 'UP-AGR', is_active: true, last_login: null, created_at: '2024-02-01T00:00:00Z', updated_at: '2024-02-01T00:00:00Z' },
  },
  viewer_anand: {
    password: 'Viewer@1234',
    user: { id: 'u-004', username: 'viewer_anand', email: 'anand.g@bhumi.gov.in', full_name: 'Anand Gupta', role: 'VIEWER', district_code: 'MH-PNE', is_active: true, last_login: new Date(Date.now() - 86400000).toISOString(), created_at: '2024-03-01T00:00:00Z', updated_at: '2024-03-01T00:00:00Z' },
  },
};

// ── Land Records ──────────────────────────────────────────────
const DISTRICTS = ['Lucknow', 'Agra', 'Varanasi', 'Allahabad', 'Kanpur', 'Pune', 'Nashik', 'Jaipur', 'Jodhpur', 'Mysuru'];
const TEHSILS   = ['Sadar', 'Kotwali', 'Civil Lines', 'Cantonment', 'Vrindavan', 'Dehat'];
const VILLAGES  = ['Rampur', 'Krishnanagar', 'Sitapur', 'Lakshmipur', 'Govindpur', 'Shivnagar', 'Ganga Nagar', 'Arjunpur'];
const STATES    = ['Uttar Pradesh', 'Maharashtra', 'Rajasthan', 'Karnataka', 'Gujarat', 'Madhya Pradesh'];
const OWNERS    = ['Ramesh Prasad', 'Sita Devi', 'Mohanlal Yadav', 'Usha Sharma', 'Dinesh Kumar', 'Kavita Singh', 'Suresh Verma', 'Poonam Gupta', 'Ajay Tiwari', 'Meena Rawat', 'Bharat Lal', 'Kamla Bai', 'Santosh Mishra', 'Rekha Patel', 'Vinod Chauhan'];
const LAND_USES = ['AGRICULTURAL', 'RESIDENTIAL', 'COMMERCIAL', 'FOREST', 'INDUSTRIAL', 'WASTELAND'] as const;
const STATUSES  = ['PENDING', 'UNDER_REVIEW', 'VERIFIED', 'REJECTED', 'ARCHIVED'] as const;

function rand<T>(arr: readonly T[]): T { return arr[Math.floor(Math.random() * arr.length)]; }
function randFloat(min: number, max: number): number { return Math.round((Math.random() * (max - min) + min) * 10000) / 10000; }
function daysAgo(n: number): string { return new Date(Date.now() - n * 86400000).toISOString(); }

let _records: LandRecord[] | null = null;
export function getMockRecords(): LandRecord[] {
  if (_records) return _records;
  const statuses: LandRecord['status'][] = ['PENDING','PENDING','UNDER_REVIEW','VERIFIED','VERIFIED','VERIFIED','REJECTED','ARCHIVED'];
  _records = Array.from({ length: 248 }, (_, i) => {
    const id = `rec-${String(i + 1).padStart(4, '0')}`;
    const st = statuses[i % statuses.length];
    const district = DISTRICTS[i % DISTRICTS.length];
    const stateVal = STATES[i % STATES.length];
    const daysOld = Math.floor(Math.random() * 120) + 1;
    return {
      id,
      khasra_number: `KH-${String(10000 + i).padStart(5,'0')}`,
      khatauni_number: `KT-${String(5000 + i).padStart(4,'0')}`,
      survey_number: `SUR-${200 + (i % 800)}`,
      state: stateVal,
      district,
      tehsil: TEHSILS[i % TEHSILS.length],
      village: VILLAGES[i % VILLAGES.length],
      pin_code: String(200000 + (i * 37) % 800000),
      area_hectares: randFloat(0.05, 12.5),
      land_use_type: LAND_USES[i % LAND_USES.length],
      owner_name: OWNERS[i % OWNERS.length],
      father_name: OWNERS[(i + 3) % OWNERS.length],
      address: `${Math.floor(Math.random()*500)+1}, ${VILLAGES[i % VILLAGES.length]}, ${district}`,
      aadhaar_last4: String(1000 + (i * 7) % 9000),
      status: st,
      rejection_reason: st === 'REJECTED' ? 'Survey number mismatch with revenue records' : null,
      geometry: null,
      created_by: 'u-002',
      verified_by: st === 'VERIFIED' ? 'u-003' : null,
      verified_at: st === 'VERIFIED' ? daysAgo(daysOld - 2) : null,
      created_at: daysAgo(daysOld),
      updated_at: daysAgo(Math.floor(daysOld / 2)),
    };
  });
  return _records;
}

export function getMockListItems(): LandRecordListItem[] {
  return getMockRecords().map(r => ({
    id: r.id, khasra_number: r.khasra_number, owner_name: r.owner_name,
    district: r.district, village: r.village, area_hectares: r.area_hectares,
    land_use_type: r.land_use_type, status: r.status,
    created_at: r.created_at, updated_at: r.updated_at,
  }));
}

export const MOCK_DASHBOARD_STATS: DashboardStats = {
  records: { total: 248, pending: 71, under_review: 35, verified: 108, rejected: 22 },
  users: { total: 24 },
  documents: { total: 516 },
  disclaimer: 'All data is synthetic — demo system only.',
};

// ── Documents ─────────────────────────────────────────────────
export type DocType = 'TITLE_DEED' | 'SURVEY_MAP' | 'MUTATION_ORDER' | 'ENCUMBRANCE_CERT' | 'TAX_RECEIPT';
export type DocStatus = 'UPLOADED' | 'PROCESSING' | 'VALIDATED' | 'REJECTED';

export interface MockDocument {
  id: string; land_record_id: string; khasra_number: string; owner_name: string;
  document_type: DocType; original_filename: string; file_size_bytes: number;
  mime_type: string; status: DocStatus; confidence?: number;
  validation_notes: string | null; uploaded_at: string; uploaded_by: string;
}

const DOC_TYPES: DocType[] = ['TITLE_DEED', 'SURVEY_MAP', 'MUTATION_ORDER', 'ENCUMBRANCE_CERT', 'TAX_RECEIPT'];
const DOC_STATUSES: DocStatus[] = ['UPLOADED', 'PROCESSING', 'VALIDATED', 'VALIDATED', 'VALIDATED', 'REJECTED'];

let _docs: MockDocument[] | null = null;
export function getMockDocuments(): MockDocument[] {
  if (_docs) return _docs;
  const records = getMockRecords().slice(0, 60);
  _docs = records.flatMap((r, ri) =>
    Array.from({ length: Math.floor(Math.random() * 3) + 1 }, (_, di) => ({
      id: `doc-${ri}-${di}`,
      land_record_id: r.id,
      khasra_number: r.khasra_number,
      owner_name: r.owner_name,
      document_type: DOC_TYPES[(ri + di) % DOC_TYPES.length],
      original_filename: `${r.khasra_number}_${DOC_TYPES[(ri + di) % DOC_TYPES.length].toLowerCase()}.pdf`,
      file_size_bytes: Math.floor(Math.random() * 4000000) + 100000,
      mime_type: 'application/pdf',
      status: DOC_STATUSES[(ri + di) % DOC_STATUSES.length],
      confidence: DOC_STATUSES[(ri + di) % DOC_STATUSES.length] === 'VALIDATED' ? Math.round(75 + Math.random() * 25) : undefined,
      validation_notes: DOC_STATUSES[(ri + di) % DOC_STATUSES.length] === 'REJECTED' ? 'Document quality insufficient for OCR extraction' : null,
      uploaded_at: daysAgo(Math.floor(Math.random() * 90) + 1),
      uploaded_by: 'officer_rajesh',
    }))
  );
  return _docs;
}

// ── Audit logs ────────────────────────────────────────────────
export interface AuditEvent {
  id: string; timestamp: string; action: string; actor: string;
  actor_role: string; resource_type: string; resource_id: string;
  description: string; status: 'SUCCESS' | 'ERROR'; ip: string;
}

const AUDIT_ACTIONS = [
  { action: 'LOGIN', desc: 'User signed in to portal' },
  { action: 'CREATE_RECORD', desc: 'New land record created' },
  { action: 'VERIFY_RECORD', desc: 'Land record verified and approved' },
  { action: 'REJECT_RECORD', desc: 'Land record rejected' },
  { action: 'UPLOAD_DOCUMENT', desc: 'Document uploaded for processing' },
  { action: 'VALIDATE_DOCUMENT', desc: 'Document validated by verifier' },
  { action: 'UPDATE_RECORD', desc: 'Land record details updated' },
  { action: 'EXPORT_REPORT', desc: 'Report exported as PDF' },
];

let _audit: AuditEvent[] | null = null;
export function getMockAuditEvents(): AuditEvent[] {
  if (_audit) return _audit;
  const users = Object.values(MOCK_USERS);
  _audit = Array.from({ length: 120 }, (_, i) => {
    const ev = AUDIT_ACTIONS[i % AUDIT_ACTIONS.length];
    const u = users[i % users.length].user;
    return {
      id: `aud-${i}`, timestamp: daysAgo(Math.random() * 30),
      action: ev.action, actor: u.full_name, actor_role: u.role,
      resource_type: ev.action.includes('DOCUMENT') ? 'Document' : 'LandRecord',
      resource_id: `rec-${String(i + 1).padStart(4, '0')}`,
      description: ev.desc, status: i % 15 === 0 ? 'ERROR' : 'SUCCESS',
      ip: `10.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}.${Math.floor(Math.random()*255)}`,
    };
  });
  return _audit.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

// ── Anomalies ─────────────────────────────────────────────────
export type AnomalyType = 'AREA_MISMATCH' | 'DUPLICATE_KHASRA' | 'OWNER_CONFLICT' | 'BOUNDARY_OVERLAP' | 'MISSING_FIELD' | 'INVALID_SURVEY';
export type AnomalySeverity = 'HIGH' | 'MEDIUM' | 'LOW';

export interface Anomaly {
  id: string; record_id: string; khasra_number: string; anomaly_type: AnomalyType;
  severity: AnomalySeverity; description: string; detected_at: string;
  resolved: boolean; confidence: number;
}

const ANOMALY_TYPES: AnomalyType[] = ['AREA_MISMATCH','DUPLICATE_KHASRA','OWNER_CONFLICT','BOUNDARY_OVERLAP','MISSING_FIELD','INVALID_SURVEY'];
const ANOMALY_DESCS: Record<AnomalyType, string> = {
  AREA_MISMATCH: 'Reported area deviates >15% from satellite measurement',
  DUPLICATE_KHASRA: 'Khasra number already exists in another district',
  OWNER_CONFLICT: 'Owner details conflict with mutation records',
  BOUNDARY_OVERLAP: 'Parcel boundary overlaps with adjacent record',
  MISSING_FIELD: 'Required survey number field is empty',
  INVALID_SURVEY: 'Survey number does not match revenue department format',
};

let _anomalies: Anomaly[] | null = null;
export function getMockAnomalies(): Anomaly[] {
  if (_anomalies) return _anomalies;
  const records = getMockRecords();
  _anomalies = Array.from({ length: 38 }, (_, i) => {
    const type = ANOMALY_TYPES[i % ANOMALY_TYPES.length];
    const r = records[i * 5 % records.length];
    return {
      id: `anom-${i}`, record_id: r.id, khasra_number: r.khasra_number,
      anomaly_type: type,
      severity: i % 3 === 0 ? 'HIGH' : i % 3 === 1 ? 'MEDIUM' : 'LOW',
      description: ANOMALY_DESCS[type],
      detected_at: daysAgo(Math.floor(Math.random() * 14)),
      resolved: i % 5 === 0, confidence: Math.round(65 + Math.random() * 35),
    };
  });
  return _anomalies;
}

// ── Verification Queue ────────────────────────────────────────
export function getVerificationQueue(): LandRecord[] {
  return getMockRecords().filter(r => r.status === 'PENDING' || r.status === 'UNDER_REVIEW').slice(0, 30);
}
