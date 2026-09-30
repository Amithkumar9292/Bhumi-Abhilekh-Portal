/**
 * Document intake — where the operator lands after uploading.
 *
 * Uploading is done to see what was read out of the document, so once the
 * pipeline reaches a finished state the page used to stop on a summary panel
 * and make the operator click through to the review screen. The comment in the
 * source even said "go straight to the review screen" while the code only set
 * phase='done'. These tests pin the redirect.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { DocumentIntakePage } from '../pages/DocumentIntakePage';
import { intakeApi, type IntakeUploadResponse } from '../api/intake';
import type { JobStatus } from '../types/document';

const REDIRECT_TIMEOUT_MS = 5000;
const TEST_TIMEOUT_MS = 20000;

const UPLOAD = {
  document_id: 'doc-1',
  job_id: 'job-1',
  land_record_id: 'rec-1',
  new_record_created: true,
  khasra_matched: false,
  filename: 'khasra.png',
  file_size_bytes: 2048,
  status: 'queued',
  stage: 'QUEUED',
  progress: 0,
} as IntakeUploadResponse;

function jobStatus(over: Partial<JobStatus> = {}): JobStatus {
  return {
    job_id: 'job-1',
    document_id: 'doc-1',
    source: 'db',
    status: 'processing',
    stage_status: 'OCR_RUNNING',
    stage: 'OCR',
    message: 'Running OCR',
    progress: 40,
    failed_stage: null,
    error_type: null,
    ...over,
  } as JobStatus;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/intake']}>
      <Routes>
        <Route path="/intake" element={<DocumentIntakePage />} />
        <Route path="/intake/review/:jobId" element={<div>REVIEW SCREEN for job</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** Select a file and submit, then wait for the upload to be accepted. */
async function uploadAndSubmit() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(['fake-png-bytes'], 'khasra.png', { type: 'image/png' });
  await userEvent.upload(input, file);

  // Document type is a required form field.
  const typeSelect = document.querySelector('select') as HTMLSelectElement;
  await userEvent.selectOptions(typeSelect, 'SURVEY_MAP');

  const submit = screen.getByRole('button', { name: /upload|process|submit/i });
  await userEvent.click(submit);
  await waitFor(() => expect(intakeApi.upload).toHaveBeenCalled());
}

describe('DocumentIntakePage redirect after upload', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(intakeApi, 'upload').mockResolvedValue(UPLOAD);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('sends the operator to the review screen when verification is required', async () => {
    vi.spyOn(intakeApi, 'pollStatus').mockResolvedValue(
      jobStatus({ status: 'verification_required', progress: 94, stage: 'VERIFICATION_REQUIRED' }),
    );

    renderPage();
    await uploadAndSubmit();

    await waitFor(
      () => expect(screen.getByText('REVIEW SCREEN for job')).toBeInTheDocument(),
      { timeout: REDIRECT_TIMEOUT_MS },
    );
  }, TEST_TIMEOUT_MS);

  it('also sends the operator to the review screen when the job completes', async () => {
    // A fully auto-valid document has nothing to confirm, but the extracted
    // fields are still what the operator uploaded it to see.
    vi.spyOn(intakeApi, 'pollStatus').mockResolvedValue(
      jobStatus({ status: 'completed', progress: 100, stage: 'COMPLETED' }),
    );

    renderPage();
    await uploadAndSubmit();

    await waitFor(
      () => expect(screen.getByText('REVIEW SCREEN for job')).toBeInTheDocument(),
      { timeout: REDIRECT_TIMEOUT_MS },
    );
  }, TEST_TIMEOUT_MS);

  it('keeps the user on the intake page while the job is still running', async () => {
    vi.spyOn(intakeApi, 'pollStatus').mockResolvedValue(jobStatus());

    renderPage();
    await uploadAndSubmit();

    // The progress UI is still up; no redirect yet.
    await waitFor(() => expect(screen.queryByText('REVIEW SCREEN for job')).not.toBeInTheDocument());
    expect(screen.getByText(/running ocr|processing/i)).toBeInTheDocument();
  }, TEST_TIMEOUT_MS);

  it('does not redirect away a failed job', async () => {
    // A failure has nothing to review; the operator needs the error and a
    // chance to re-upload.
    vi.spyOn(intakeApi, 'pollStatus').mockResolvedValue(
      jobStatus({
        status: 'failed',
        failed_stage: 'OCR',
        error_type: 'OCRBackendUnavailable',
        error_message: 'tesseract missing',
        message: 'tesseract missing',
      }),
    );

    renderPage();
    await uploadAndSubmit();

    // The first poll does not fire until POLL_INTERVAL_MS has elapsed.
    await waitFor(
      () => expect(screen.getByText(/tesseract missing/i)).toBeInTheDocument(),
      { timeout: REDIRECT_TIMEOUT_MS },
    );
    expect(screen.queryByText('REVIEW SCREEN for job')).not.toBeInTheDocument();
  }, TEST_TIMEOUT_MS);

  it('stops polling once it has redirected', async () => {
    const poll = vi.spyOn(intakeApi, 'pollStatus').mockResolvedValue(
      jobStatus({ status: 'verification_required', progress: 94, stage: 'VERIFICATION_REQUIRED' }),
    );

    renderPage();
    await uploadAndSubmit();

    await waitFor(
      () => expect(screen.getByText('REVIEW SCREEN for job')).toBeInTheDocument(),
      { timeout: REDIRECT_TIMEOUT_MS },
    );
    const callsAtRedirect = poll.mock.calls.length;

    // A terminal job must not keep hammering the status endpoint. The page
    // polls every 2s, so wait well past one interval.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 5000));
    });
    expect(poll.mock.calls.length).toBe(callsAtRedirect);
  }, TEST_TIMEOUT_MS);
});
