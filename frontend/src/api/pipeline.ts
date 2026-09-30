/**
 * Pipeline API: the real processing jobs, their extracted fields and anomalies.
 *
 * The pipeline page previously rendered four hardcoded jobs, so it showed a
 * fictional OCR backend and stale numbers regardless of what had actually been
 * uploaded. Everything here is real data from the processing_jobs table.
 */
import apiClient, { POLL_TIMEOUT_MS } from './client';
import type { JobState, PipelineStage } from '../types/document';

/** One row in the pipeline queue. */
export interface PipelineJobListItem {
  id: string;
  document_id: string;
  /** Coarse lifecycle, lowercase. */
  status: JobState;
  stage: PipelineStage | string | null;
  stage_status: string;
  progress_pct: number;
  message: string | null;
  failed_stage: string | null;
  error_type: string | null;
  error_message: string | null;
  /** 0-1 fraction, or null. */
  overall_confidence: number | null;
  verification_status: string | null;
  needs_human_review: boolean;
  has_anomalies: boolean;
  is_duplicate: boolean;
  detected_language: string | null;
  page_count: number | null;
  /** 0-1 fraction, or null. */
  image_quality_score: number | null;
  document_name: string | null;
  document_type: string | null;
  khasra_number: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface PipelineJobListResponse {
  items: PipelineJobListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface PipelineField {
  id: string;
  field_name: string;
  field_display: string | null;
  raw_value: string | null;
  normalized_value: string | null;
  confidence_score: number;
  ocr_confidence: number | null;
  extraction_method: string | null;
  source_page: number | null;
  validation_status: string;
  validation_message: string | null;
  needs_review: boolean;
  verified_by: string | null;
  verified_value: string | null;
  verified_at: string | null;
}

export interface PipelineAnomaly {
  id: string;
  anomaly_type: string;
  field_name: string | null;
  severity: string;
  description: string;
  confidence: number;
  resolved: boolean;
  created_at: string;
}

/**
 * An anomaly joined to the scan it was found in.
 *
 * The bare anomaly row answers "what is wrong"; this one also answers "which
 * uploaded file and which Khasra is it wrong about", which is what the anomaly
 * screen has to show.
 */
export interface AnomalyFeedItem extends PipelineAnomaly {
  job_id: string;
  document_id: string;
  document_name: string;
  document_type: string;
  land_record_id: string | null;
  khasra_number: string | null;
  village: string | null;
  district: string | null;
  /** confidence as 0-100, ready to render. */
  confidence_pct: number;
  resolved_by: string | null;
}

export interface AnomalyFeedResponse {
  items: AnomalyFeedItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** Full job detail: everything GET /pipeline/jobs/{id} returns. */
export interface PipelineJobDetail {
  id: string;
  document_id: string;
  land_record_id: string | null;
  status: string;
  current_stage: PipelineStage | string | null;
  progress_pct: number;
  detected_language: string | null;
  page_count: number | null;
  image_quality_score: number | null;
  overall_confidence: number | null;
  needs_human_review: boolean;
  has_anomalies: boolean;
  is_duplicate: boolean;
  duplicate_of_id: string | null;
  error_message: string | null;
  stage_timings: Record<string, number> | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  extracted_fields: PipelineField[];
  anomalies: PipelineAnomaly[];
  verification_tasks: { id: string; field_id: string; status: string; priority: string }[];
}

export const pipelineApi = {
  /** The job queue, newest first. */
  listJobs: async (params?: {
    page?: number;
    page_size?: number;
    status?: string;
  }): Promise<PipelineJobListResponse> => {
    const res = await apiClient.get<PipelineJobListResponse>('/pipeline/jobs', { params });
    return res.data;
  },

  /** Full job detail including extracted fields and anomalies. */
  getJob: async (jobId: string): Promise<PipelineJobDetail> => {
    const res = await apiClient.get<PipelineJobDetail>(`/pipeline/jobs/${jobId}`, {
      timeout: POLL_TIMEOUT_MS,
    });
    return res.data;
  },

  /** Record a verifier's correction for one extracted field. */
  verifyField: async (fieldId: string, verifiedValue: string, notes?: string) => {
    const res = await apiClient.post(`/pipeline/fields/${fieldId}/verify`, {
      verified_value: verifiedValue,
      notes,
    });
    return res.data;
  },

  /** Requeue a failed job. */
  retryJob: async (jobId: string) => {
    const res = await apiClient.post(`/pipeline/jobs/${jobId}/retry`);
    return res.data;
  },

  /**
   * The anomaly log, each finding tied back to its document and land record.
   */
  listAnomalies: async (params?: {
    severity?: string;
    anomaly_type?: string;
    resolved?: boolean;
    land_record_id?: string;
    page?: number;
    page_size?: number;
  }): Promise<AnomalyFeedResponse> => {
    const res = await apiClient.get<AnomalyFeedResponse>('/pipeline/anomalies/feed', { params });
    return res.data;
  },

  /** Mark one anomaly as resolved (VERIFIER or ADMIN). */
  resolveAnomaly: async (anomalyId: string) => {
    const res = await apiClient.post(`/pipeline/anomalies/${anomalyId}/resolve`);
    return res.data;
  },
};
