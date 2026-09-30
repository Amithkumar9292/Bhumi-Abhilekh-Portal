export type RecordStatus = 'PENDING' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'ARCHIVED';
export type LandUseType  = 'AGRICULTURAL' | 'RESIDENTIAL' | 'COMMERCIAL' | 'FOREST' | 'INDUSTRIAL' | 'WASTELAND';

export interface LandRecord {
  id: string;
  khasra_number: string;
  khatauni_number: string;
  survey_number: string;
  state: string;
  district: string;
  tehsil: string;
  village: string;
  pin_code: string;
  area_hectares: number;
  land_use_type: LandUseType;
  owner_name: string;
  // The API returns nulls for anything OCR did not pick up, so these are
  // nullable in the read model even though the create payload requires them.
  father_name: string | null;
  address: string | null;
  aadhaar_last4: string | null;
  status: RecordStatus;
  rejection_reason: string | null;
  geometry: Record<string, unknown> | null;
  created_by: string;
  verified_by: string | null;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LandRecordListItem {
  id: string;
  khasra_number: string;
  owner_name: string;
  district: string;
  village: string;
  area_hectares: number;
  land_use_type: LandUseType;
  status: RecordStatus;
  created_at: string;
  updated_at: string;
}

export interface DashboardStats {
  records: {
    total: number;
    pending: number;
    under_review: number;
    verified: number;
    rejected: number;
  };
  users: { total: number };
  documents: { total: number };
  disclaimer: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface LandRecordCreate {
  khasra_number: string;
  khatauni_number: string;
  survey_number: string;
  state: string;
  district: string;
  tehsil: string;
  village: string;
  pin_code: string;
  area_hectares: number;
  land_use_type: LandUseType;
  owner_name: string;
  father_name: string;
  address: string;
  aadhaar_last4: string;
}

export interface RecentActivity {
  id: string;
  type: string;
  title: string;
  description: string;
  timestamp: string;
}
