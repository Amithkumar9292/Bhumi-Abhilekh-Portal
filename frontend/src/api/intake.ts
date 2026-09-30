/**
 * Intake API — wraps the /intake/* endpoints.
 *
 * The upload is non-blocking: it stores the file, creates a QUEUED job and
 * returns 202 straight away. All OCR and field extraction then happen in a
 * background worker, so the client polls for status instead of waiting:
 *
 *   1. POST /intake/upload → 202 { document_id, job_id, land_record_id, status: "queued" }
 *   2. Poll GET /pipeline/jobs/{job_id}/status until the status is terminal
 *      (completed / failed / verification_required)
 *   3. GET /intake/review/{job_id} → full review payload
 *   4. POST /intake/confirm/{job_id}/submit → save with corrections
 */

import apiClient, { POLL_TIMEOUT_MS, UPLOAD_TIMEOUT_MS } from './client';
import type { DocumentType, JobState, JobStatus, PipelineStage } from '../types/document';
import { describeApiError } from '../utils/errors';

// ── Upload response ─────────────────────────────────────────────────────────
export interface IntakeUploadResponse {
  document_id: string;
  job_id: string;
  land_record_id: string;
  new_record_created: boolean;
  khasra_matched: boolean;
  filename: string;
  file_size_bytes: number;
  status: string;
  stage: string;
  progress: number;
  message: string;
  status_url: string;
  job_status_url: string;
  review_url: string;
  /**
   * Set when the queue was unreachable and the API ran the pipeline in-process
   * as a fallback. The job still processes, but it will not survive a restart.
   */
  queue_warning?: string | null;
}

// ── Extracted field ──────────────────────────────────────────────────────────
export interface ExtractedField {
  id: string;
  field_name: string;
  field_display: string | null;
  raw_value: string | null;
  normalized_value: string | null;
  confidence_score: number;
  confidence_pct: number;
  ocr_confidence: number | null;
  extraction_method: string | null;
  source_page: number | null;
  bounding_box: Record<string, number> | null;
  validation_status: string;
  validation_message: string | null;
  needs_review: boolean;
  verified_value: string | null;
  verified_at: string | null;
}

// ── Review response ─────────────────────────────────────────────────────────
export interface IntakeReviewResponse {
  job_id: string;
  /** Coarse lifecycle: queued | processing | verification_required | completed | failed */
  status: JobState;
  current_stage: PipelineStage | null;
  stage_message: string | null;
  /** Canonical stage the job failed in, when status is "failed". */
  failed_stage: string | null;
  error_type: string | null;
  progress_pct: number;
  detected_language: string | null;
  page_count: number | null;
  image_quality_score: number | null;
  overall_confidence: number | null;
  overall_confidence_pct: number;
  verification_status: string | null;
  needs_human_review: boolean;
  has_anomalies: boolean;
  is_duplicate: boolean;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  document: {
    id: string;
    original_filename: string;
    document_type: string;
    file_size_bytes: number;
    mime_type: string | null;
    status: string;
    created_at: string;
  };
  land_record: {
    id: string;
    khasra_number: string;
    khatauni_number: string | null;
    survey_number: string | null;
    state: string;
    district: string;
    tehsil: string;
    village: string;
    area_hectares: number;
    land_use_type: string | null;
    owner_name: string;
    father_name: string | null;
    address: string | null;
    status: string;
  } | null;
  extracted_fields: ExtractedField[];
  anomalies: Array<{
    id: string;
    anomaly_type: string;
    field_name: string | null;
    severity: string;
    description: string;
    confidence: number;
  }>;
}

// ── Confirm payload ─────────────────────────────────────────────────────────
export interface ConfirmPayload {
  corrections: Record<string, string>;
  notes?: string;
}

export interface ConfirmResponse {
  job_id: string;
  land_record_id: string;
  document_id: string;
  khasra_number: string;
  owner_name: string;
  status: string;
  land_record_status: string;
  message: string;
}

// ── API ─────────────────────────────────────────────────────────────────────
export const intakeApi = {
  /**
   * Upload a document for intake.
   *
   * Resolves as soon as the file is stored and queued (HTTP 202) — it does not
   * wait for OCR. `khasraHint` is optional: without a match, a new draft land
   * record is created automatically.
   */
  upload: async (
    file: File,
    documentType: DocumentType,
    khasraHint?: string,
    remarks?: string,
  ): Promise<IntakeUploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('document_type', documentType);
    if (khasraHint?.trim()) form.append('khasra_hint', khasraHint.trim());
    if (remarks?.trim()) form.append('remarks', remarks.trim());

    const res = await apiClient.post<IntakeUploadResponse>('/intake/upload', form, {
      headers: { 'Content-Type': undefined },
      timeout: UPLOAD_TIMEOUT_MS,
    });
    return res.data;
  },

  /**
   * Poll pipeline status. Short timeout and no caching, since this is called
   * repeatedly and a stale answer would make the UI look stuck.
   */
  pollStatus: async (jobId: string): Promise<JobStatus> => {
    const res = await apiClient.get<JobStatus>(`/pipeline/jobs/${jobId}/status`, {
      timeout: POLL_TIMEOUT_MS,
    });
    return res.data;
  },

  /** Get the full review payload once pipeline is complete. */
  getReview: async (jobId: string): Promise<IntakeReviewResponse> => {
    const res = await apiClient.get<IntakeReviewResponse>(`/intake/review/${jobId}`);
    return res.data;
  },

  /** Submit verified/corrected values and finalize the land record. */
  confirm: async (jobId: string, payload: ConfirmPayload): Promise<ConfirmResponse> => {
    const res = await apiClient.post<ConfirmResponse>(
      `/intake/confirm/${jobId}/submit`,
      payload,
    );
    return res.data;
  },
};

/** Extract a human-readable error from an Axios failure. */
export function describeIntakeError(err: unknown): string {
  return describeApiError(err);
}
