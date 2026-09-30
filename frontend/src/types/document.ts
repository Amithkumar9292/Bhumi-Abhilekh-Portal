export type DocumentType =
  | 'TITLE_DEED'
  | 'SURVEY_MAP'
  | 'TAX_RECEIPT'
  | 'MUTATION_ORDER'
  | 'COURT_ORDER'
  | 'OTHER';

export type DocumentStatus = 'UPLOADED' | 'PROCESSING' | 'VALIDATED' | 'REJECTED';

/** Persisted `processing_jobs.status` values, mirroring the backend enum. */
export type ProcessingStatus =
  | 'QUEUED'
  | 'VALIDATING'
  | 'QUALITY_ANALYSIS'
  | 'PREPROCESSING'
  | 'OCR_RUNNING'
  | 'LANGUAGE_DETECTION'
  | 'EXTRACTING'
  | 'CLASSIFYING'
  | 'SCORING'
  | 'DEDUP_CHECK'
  | 'ANOMALY_CHECK'
  | 'PENDING_REVIEW'
  | 'COMPLETED'
  | 'FAILED';

/**
 * Coarse lifecycle reported as `status` by the status endpoints.
 *
 * `verification_required` is not `processing` and not `completed`: automated
 * work has finished, but a human must confirm low-confidence fields, so the UI
 * routes to the review screen and stops polling.
 */
export type JobState =
  | 'queued'
  | 'processing'
  | 'verification_required'
  | 'completed'
  | 'failed';

/** Canonical stage names reported as `stage`, in pipeline order. */
export type PipelineStage =
  | 'QUEUED'
  | 'FILE_VALIDATION'
  | 'IMAGE_QUALITY'
  | 'PREPROCESSING'
  | 'OCR'
  | 'LANGUAGE_DETECTION'
  | 'FIELD_EXTRACTION'
  | 'CLASSIFICATION'
  | 'CONFIDENCE_SCORING'
  | 'VALIDATION'
  | 'DUPLICATE_CHECK'
  | 'ANOMALY_CHECK'
  | 'VERIFICATION_REQUIRED'
  | 'COMPLETED'
  | 'FAILED';

/** No further automated work will run; stop polling. */
export const TERMINAL_JOB_STATES: ReadonlySet<JobState> = new Set<JobState>([
  'completed',
  'failed',
  'verification_required',
]);

/** States that mean the pipeline is still doing work. */
export const ACTIVE_JOB_STATES: ReadonlySet<JobState> = new Set<JobState>([
  'queued',
  'processing',
]);

/** Response from POST /api/v1/documents/upload. */
export interface UploadResponse {
  id: string;
  original_filename: string;
  document_type: DocumentType;
  file_size_bytes: number;
  status: DocumentStatus;
  created_at: string;
  pipeline_job_id?: string;
  pipeline_status?: ProcessingStatus;
  message?: string;
}

/** Response from GET /api/v1/pipeline/jobs/{job_id}/status. */
export interface JobStatus {
  job_id: string;
  document_id: string;
  source: 'cache' | 'db';
  /** Coarse lifecycle to branch on. */
  status: JobState;
  /** Coarse lifecycle as persisted, for display alongside the stage. */
  stage_status: ProcessingStatus;
  /** Precise stage currently running, e.g. "OCR". */
  stage: PipelineStage | string;
  stage_status_message?: string;
  message: string;
  progress: number;
  failed_stage: string | null;
  error_type: string | null;
  error_message: string | null;
  overall_confidence: number | null;
  verification_status: string | null;
  detected_language: string | null;
  page_count: number | null;
  needs_human_review: boolean | null;
  has_anomalies: boolean | null;
  is_duplicate: boolean | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

/** Mirrors the document_type_enum PostgreSQL type. */
export const DOCUMENT_TYPES: ReadonlyArray<{ value: DocumentType; label: string }> = [
  { value: 'TITLE_DEED', label: 'Title Deed' },
  { value: 'SURVEY_MAP', label: 'Survey Map / Khasra Nakal' },
  { value: 'MUTATION_ORDER', label: 'Mutation Order (Dakhil Kharij)' },
  { value: 'COURT_ORDER', label: 'Court Order' },
  { value: 'TAX_RECEIPT', label: 'Land Tax Receipt' },
  { value: 'OTHER', label: 'Other' },
];
