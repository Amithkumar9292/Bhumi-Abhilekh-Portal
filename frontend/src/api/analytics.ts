/**
 * Analytics API — the numbers behind the Reports screen.
 *
 * These used to be literals in ReportsPage, which meant the report described a
 * system nobody had uploaded anything into. Every endpoint here aggregates the
 * tables the intake pipeline writes, so a finished upload shows up immediately.
 */
import apiClient from './client';

export interface KpiSnapshot {
  records: {
    total: number;
    verified: number;
    pending: number;
    under_review: number;
    rejected: number;
    verification_rate_pct: number;
  };
  documents: {
    total: number;
    processed: number;
    processing_rate_pct: number;
    uploaded_last_24h: number;
    records_from_upload: number;
  };
  pipeline: {
    total_jobs: number;
    failed: number;
    pending_review: number;
    success_rate_pct: number;
  };
  area: { total_hectares: number };
  anomalies: { open: number };
  users: { active: number };
  as_of: string;
  disclaimer: string;
}

export interface StatusDatum {
  status: string;
  count: number;
}

export interface DistrictDatum {
  district: string;
  state: string;
  count: number;
  total_area_ha: number;
}

export interface StateDatum {
  state: string;
  count: number;
  verified: number;
  total_area_ha: number;
}

export interface LandUseDatum {
  land_use: string;
  count: number;
  total_area_ha: number;
}

export interface ThroughputDatum {
  date: string | null;
  total: number;
  completed: number;
  failed: number;
}

export interface AreaBucket {
  range: string;
  count: number;
}

export interface AnomalyTrendDatum {
  type: string;
  severity: string;
  count: number;
}

export interface DocumentsSummary {
  by_status: Array<{ status: string; count: number }>;
  by_type: Array<{ document_type: string; count: number }>;
  records_from_upload: number;
  records_with_anomalies: number;
}

export interface ValidationHealthDatum {
  field_name: string;
  total: number;
  auto_valid: number;
  auto_invalid: number;
  human_verified: number;
  human_rejected: number;
  needs_review: number;
  accepted: number;
  rejected: number;
  pass_rate_pct: number;
}

export interface FieldAccuracyDatum {
  field_name: string;
  field_display: string;
  samples: number;
  extracted: number;
  found_rate_pct: number;
  avg_confidence_pct: number;
  avg_ocr_confidence_pct: number;
}

export interface OfficerActivityDatum {
  name: string;
  role: string;
  username: string;
  records_created: number;
}

const unwrap = <T>(data: { data: T[] }): T[] => data.data;

export const analyticsApi = {
  getKpis: async (): Promise<KpiSnapshot> => {
    const res = await apiClient.get<KpiSnapshot>('/analytics/kpis');
    return res.data;
  },

  getRecordsByStatus: async (): Promise<StatusDatum[]> => {
    const res = await apiClient.get<{ data: StatusDatum[] }>('/analytics/records-by-status');
    return unwrap(res.data);
  },

  getRecordsByDistrict: async (limit = 15): Promise<DistrictDatum[]> => {
    const res = await apiClient.get<{ data: DistrictDatum[] }>('/analytics/records-by-district', {
      params: { limit },
    });
    return unwrap(res.data);
  },

  getRecordsByState: async (limit = 20): Promise<StateDatum[]> => {
    const res = await apiClient.get<{ data: StateDatum[] }>('/analytics/records-by-state', {
      params: { limit },
    });
    return unwrap(res.data);
  },

  getRecordsByLandUse: async (): Promise<LandUseDatum[]> => {
    const res = await apiClient.get<{ data: LandUseDatum[] }>('/analytics/records-by-land-use');
    return unwrap(res.data);
  },

  getProcessingThroughput: async (days = 30): Promise<ThroughputDatum[]> => {
    const res = await apiClient.get<{ data: ThroughputDatum[] }>('/analytics/processing-throughput', {
      params: { days },
    });
    return unwrap(res.data);
  },

  getAreaDistribution: async (): Promise<AreaBucket[]> => {
    const res = await apiClient.get<{ data: AreaBucket[] }>('/analytics/area-distribution');
    return unwrap(res.data);
  },

  getAnomalyTrends: async (): Promise<AnomalyTrendDatum[]> => {
    const res = await apiClient.get<{ data: AnomalyTrendDatum[] }>('/analytics/anomaly-trends');
    return unwrap(res.data);
  },

  /** Where every uploaded document currently sits in the pipeline. */
  getDocumentsSummary: async (): Promise<DocumentsSummary> => {
    const res = await apiClient.get<DocumentsSummary>('/analytics/documents');
    return res.data;
  },

  /** Pass/fail per extracted field, as recorded by the pipeline. */
  getValidationHealth: async (): Promise<ValidationHealthDatum[]> => {
    const res = await apiClient.get<{ data: ValidationHealthDatum[] }>('/analytics/validation-health');
    return unwrap(res.data);
  },

  /** Mean confidence per extracted field. */
  getFieldAccuracy: async (): Promise<{ data: FieldAccuracyDatum[]; overall_confidence_pct: number }> => {
    const res = await apiClient.get<{ data: FieldAccuracyDatum[]; overall_confidence_pct: number }>(
      '/analytics/field-accuracy',
    );
    return res.data;
  },

  getOfficerActivity: async (days = 30): Promise<OfficerActivityDatum[]> => {
    const res = await apiClient.get<{ data: OfficerActivityDatum[] }>('/analytics/officer-activity', {
      params: { days },
    });
    return unwrap(res.data);
  },
};
