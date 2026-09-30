import apiClient, { POLL_TIMEOUT_MS, UPLOAD_TIMEOUT_MS } from './client';
import type {
  DocumentType,
  JobState,
  JobStatus,
  PipelineStage,
  ProcessingStatus,
  UploadResponse,
} from '../types/document';
import type { LandRecordListItem, PaginatedResponse } from '../types/land';

// ── Shape returned by GET /documents ──────────────────────────────────────────
export interface DocumentListItem {
  id: string;
  land_record_id: string;
  document_type: DocumentType;
  original_filename: string;
  file_size_bytes: number;
  mime_type: string | null;
  /** Upload lifecycle: UPLOADED | PROCESSING | VALIDATED | REJECTED. */
  status: string;
  validation_notes: string | null;
  created_at: string;
  khasra_number: string | null;
  survey_number: string | null;
  owner_name: string | null;
  uploader_username: string | null;

  // Processing lifecycle, joined from the document's latest job.
  job_id: string | null;
  /** Coarse lifecycle, or null when the document was never processed. */
  processing_status: JobState | null;
  current_stage: PipelineStage | string | null;
  stage_message: string | null;
  progress_pct: number | null;
  failed_stage: string | null;
  error_type: string | null;
  error_message: string | null;
  /** Overall confidence as a percentage (0-100), or null. */
  confidence: number | null;
  verification_status: string | null;
  needs_human_review: boolean | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/** Response from GET /documents/{id}/status. */
export interface DocumentStatusResponse {
  document_id: string;
  job_id: string | null;
  /** Coarse lifecycle, or null when no job exists. */
  status: JobState | null;
  status_detail: ProcessingStatus | null;
  stage: PipelineStage | string | null;
  stage_message: string | null;
  progress_pct: number;
  failed_stage: string | null;
  error_type: string | null;
  error_message: string | null;
  confidence: number | null;
  verification_status: string | null;
  needs_human_review: boolean | null;
  has_anomalies: boolean | null;
  is_duplicate: boolean | null;
  detected_language: string | null;
  page_count: number | null;
  document_status: string;
  message: string;
}

export interface DocumentContentResponse {
  document: {
    id: string;
    original_filename: string;
    document_type: string;
    file_size_bytes: number | null;
    mime_type: string | null;
    status: string;
    validation_notes: string | null;
    created_at: string;
    /** False when the stored blob is gone, so the UI can disable the download. */
    file_available: boolean;
  };
  pipeline_job: DocumentStatusResponse | null;
  extracted_fields: ExtractedContentField[];
  /** Reconstructed from the per-field raw reads; null when nothing was read. */
  raw_ocr_text: string | null;
  land_record: {
    id: string;
    khasra_number: string;
    owner_name: string;
    village: string | null;
    district: string | null;
    state: string | null;
    area_hectares: number | null;
    status: string;
  } | null;
}

export interface ExtractedContentField {
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
  validation_status: string;
  validation_message: string | null;
  needs_review: boolean;
  verified_value: string | null;
  verified_at: string | null;
}

export const documentsApi = {
  /**
   * Fetch all documents (real DB) — used by DocumentsPage.
   */
  list: async (params?: {
    page?: number;
    page_size?: number;
    document_type?: string;
    status?: string;
    search?: string;
  }): Promise<DocumentListResponse> => {
    const res = await apiClient.get<DocumentListResponse>('/documents', { params });
    return res.data;
  },

  /**
   * Upload one document and attach it to a land record.
   *
   * Sent as multipart/form-data because the file is binary. Resolves on HTTP 202
   * once the file is stored and the processing job is queued; OCR runs in a
   * background worker, so poll `documentStatus` afterwards.
   */
  upload: async (
    file: File,
    landRecordId: string,
    documentType: DocumentType,
    autoProcess = true
  ): Promise<UploadResponse> => {
    const form = new FormData();
    form.append('file', file);
    form.append('land_record_id', landRecordId);
    form.append('document_type', documentType);
    form.append('auto_process', String(autoProcess));

    const res = await apiClient.post<UploadResponse>('/documents/upload', form, {
      // Let the browser set the multipart boundary.
      headers: { 'Content-Type': undefined },
      timeout: UPLOAD_TIMEOUT_MS,
    });
    return res.data;
  },

  /** Live processing status for one document. */
  documentStatus: async (documentId: string): Promise<DocumentStatusResponse> => {
    const res = await apiClient.get<DocumentStatusResponse>(
      `/documents/${documentId}/status`,
      { timeout: POLL_TIMEOUT_MS },
    );
    return res.data;
  },

  /**
   * Everything extracted from a document: raw OCR reads, each field with its
   * confidence and validation state, the pipeline summary and the linked record.
   */
  documentContent: async (documentId: string): Promise<DocumentContentResponse> => {
    const res = await apiClient.get<DocumentContentResponse>(
      `/documents/${documentId}/content`,
      { timeout: POLL_TIMEOUT_MS },
    );
    return res.data;
  },

  /**
   * Download the original uploaded file.
   *
   * Fetched as a blob through the authenticated client rather than an <a href>,
   * because auth is a Bearer header that a plain navigation would not send.
   */
  downloadDocument: async (documentId: string, filename: string): Promise<void> => {
    const res = await apiClient.get<Blob>(`/documents/${documentId}/file`, {
      responseType: 'blob',
      timeout: UPLOAD_TIMEOUT_MS,
    });

    const url = URL.createObjectURL(res.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoke on the next tick; revoking synchronously can cancel the download
    // in some browsers before it has started reading the blob.
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
  },

  jobStatus: async (jobId: string): Promise<JobStatus> => {
    const res = await apiClient.get<JobStatus>(`/pipeline/jobs/${jobId}/status`, {
      timeout: POLL_TIMEOUT_MS,
    });
    return res.data;
  },

  /** Resolve a Khasra/survey number to a land record id. */
  findRecordByKhasra: async (khasra: string): Promise<LandRecordListItem | null> => {
    const res = await apiClient.get<PaginatedResponse<LandRecordListItem>>('/land-records', {
      params: { search: khasra, page_size: 1 },
    });
    return res.data.items[0] ?? null;
  },
};

/** Pull a human-readable message out of an axios failure. */
export function describeError(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'response' in err) {
    const { response } = err as { response?: { data?: { detail?: unknown }; status?: number } };
    const detail = response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string };
      if (first?.msg) return first.msg;
    }
    if (response?.status) return `Request failed (HTTP ${response.status}).`;
  }
  if (err instanceof Error) return err.message;
  return 'Something went wrong. Please try again.';
}
