/**
 * Intake review page — terminal-state handling.
 *
 * The page compared `review.status` against uppercase literals ('COMPLETED',
 * 'FAILED') while the API reports the coarse lowercase JobState. Nothing ever
 * matched, so the page polled every 3s forever and rendered "Still Processing"
 * instead of the review table -- even for jobs that had already finished.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { IntakeReviewPage } from '../pages/IntakeReviewPage';
import { intakeApi, type IntakeReviewResponse } from '../api/intake';

function review(overrides: Partial<IntakeReviewResponse> = {}): IntakeReviewResponse {
  return {
    job_id: 'job-1',
    status: 'verification_required',
    current_stage: 'VERIFICATION_REQUIRED',
    stage_message: 'Routing low-confidence fields to verification…',
    failed_stage: null,
    error_type: null,
    progress_pct: 94,
    detected_language: 'en',
    page_count: 1,
    image_quality_score: 82,
    overall_confidence: 0.74,
    overall_confidence_pct: 74,
    verification_status: 'PENDING',
    needs_human_review: true,
    has_anomalies: false,
    is_duplicate: false,
    error_message: null,
    started_at: null,
    completed_at: null,
    document: {
      id: 'doc-1',
      original_filename: 'khasra.png',
      document_type: 'KHASRA',
      file_size_bytes: 1024,
      mime_type: 'image/png',
      status: 'VALIDATED',
      created_at: '2026-01-01T00:00:00Z',
    },
    land_record: {
      id: 'rec-1',
      khasra_number: 'KH-10142',
      khatauni_number: null,
      survey_number: null,
      state: 'Uttar Pradesh',
      district: 'Lucknow',
      tehsil: null,
      village: null,
      pin_code: null,
      area_hectares: 2.45,
      land_use_type: 'AGRICULTURAL',
      owner_name: 'Ramesh Prasad',
      father_name: null,
      address: null,
      status: 'PENDING',
    },
    anomalies: [],
    extracted_fields: [
      {
        id: 'f-1',
        job_id: 'job-1',
        field_name: 'khasra_number',
        field_display: 'Khasra Number',
        raw_value: 'KH-10142',
        normalized_value: 'KH-10142',
        confidence_score: 0.72,
        confidence_pct: 72,
        ocr_confidence: 0.9,
        extraction_method: 'regex',
        source_page: 1,
        bounding_box: null,
        validation_status: 'AUTO_VALID',
        validation_message: null,
        needs_review: true,
        verified_value: null,
        verified_at: null,
      },
    ],
    ...overrides,
  } as IntakeReviewResponse;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/intake/review/job-1']}>
      <Routes>
        <Route path="/intake/review/:jobId" element={<IntakeReviewPage />} />
        <Route path="/land-records/:id" element={<div>land record detail</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('IntakeReviewPage terminal states', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the review table for verification_required instead of a spinner', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(review());

    renderPage();

    // The extracted-value column only exists in the review table.
    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    expect(screen.getAllByText('KH-10142').length).toBeGreaterThan(0);
    expect(screen.queryByText('Still Processing')).not.toBeInTheDocument();
  });

  it('renders the review table for a completed job', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({ status: 'completed', current_stage: 'COMPLETED', progress_pct: 100 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    expect(screen.getAllByText('KH-10142').length).toBeGreaterThan(0);
    expect(screen.queryByText('Still Processing')).not.toBeInTheDocument();
  });

  it('shows the spinner only while the job is genuinely still running', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({ status: 'processing', current_stage: 'OCR', progress_pct: 20 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Still Processing')).toBeInTheDocument();
    });
  });

  it('shows a failure panel for a failed job', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({
        status: 'failed',
        current_stage: 'OCR',
        failed_stage: 'OCR',
        error_type: 'OCRBackendUnavailable',
        error_message: 'tesseract missing',
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Pipeline Failed')).toBeInTheDocument();
    });
    expect(screen.queryByText('Still Processing')).not.toBeInTheDocument();
  });

  it('does not re-poll once the job is terminal', async () => {
    vi.useFakeTimers();
    const spy = vi.spyOn(intakeApi, 'getReview').mockResolvedValue(review());
    try {
      renderPage();
      await vi.advanceTimersByTimeAsync(0);
      expect(spy).toHaveBeenCalledTimes(1);
      // Advance well past the poll interval; a terminal job must not refetch.
      await vi.advanceTimersByTimeAsync(60_000);
      expect(spy).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('keeps polling while the job is still processing', async () => {
    vi.useFakeTimers();
    const spy = vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({ status: 'processing', current_stage: 'OCR', progress_pct: 20 }),
    );
    try {
      renderPage();
      // Flush the initial fetch without relying on waitFor, which does not
      // advance fake timers.
      await vi.advanceTimersByTimeAsync(0);
      expect(spy).toHaveBeenCalledTimes(1);
      await vi.advanceTimersByTimeAsync(30_000);
      expect(spy.mock.calls.length).toBeGreaterThan(1);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe('IntakeReviewPage confirm affordance', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('offers Confirm & Save while the record still needs a human', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(review());

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /confirm & save record/i })).toBeInTheDocument();
    });
  });

  it('does not offer to re-confirm an already saved record', async () => {
    // Intake now redirects completed jobs here too, so this state is reachable.
    // A confirm button on a finalized record invites saving it twice.
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({
        status: 'completed',
        current_stage: 'COMPLETED',
        progress_pct: 100,
        verification_status: 'RESOLVED',
        needs_human_review: false,
      }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Record Saved')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /confirm & save record/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /view land record/i })).toBeInTheDocument();
  });

  it('still renders the extracted values for a completed job', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({ status: 'completed', current_stage: 'COMPLETED', progress_pct: 100 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    expect(screen.getAllByText('KH-10142').length).toBeGreaterThan(0);
  });

  it('omits the record link when no land record was created', async () => {
    vi.spyOn(intakeApi, 'getReview').mockResolvedValue(
      review({ status: 'completed', current_stage: 'COMPLETED', land_record: null }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Record Saved')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /view land record/i })).not.toBeInTheDocument();
  });
});
