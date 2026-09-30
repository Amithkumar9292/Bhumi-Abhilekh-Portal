/**
 * Pipeline page — real job data.
 *
 * The page rendered four hardcoded MOCK_JOBS and told the operator it was using
 * a "Mock OCR backend", so it showed fictional confidences and a fixed set of
 * 14 fields no matter what had been uploaded. It also invented the pipeline
 * stages (QUALITY_ANALYSIS, OCR_RUNNING, DEDUP_CHECK, HUMAN_REVIEW), which the
 * backend never emits. These tests pin it to the real API.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { PipelinePage } from '../pages/PipelinePage';
import { pipelineApi, type PipelineJobListItem, type PipelineJobDetail } from '../api/pipeline';

function listItem(overrides: Partial<PipelineJobListItem> = {}): PipelineJobListItem {
  return {
    id: 'job-1',
    document_id: 'doc-1',
    status: 'verification_required',
    stage: 'VERIFICATION_REQUIRED',
    stage_status: 'PENDING_REVIEW',
    progress_pct: 94,
    message: null,
    failed_stage: null,
    error_type: null,
    error_message: null,
    overall_confidence: 0.83,
    verification_status: 'PENDING',
    needs_human_review: true,
    has_anomalies: true,
    is_duplicate: false,
    detected_language: 'en',
    page_count: 2,
    image_quality_score: 0.87,
    document_name: 'khasra_nakal_KH-10142.pdf',
    document_type: 'TITLE_DEED',
    khasra_number: 'KH-10142',
    created_at: '2026-01-01T00:00:00Z',
    started_at: null,
    completed_at: null,
    ...overrides,
  } as PipelineJobListItem;
}

function detail(overrides: Partial<PipelineJobDetail> = {}): PipelineJobDetail {
  return {
    id: 'job-1',
    document_id: 'doc-1',
    land_record_id: 'rec-1',
    status: 'PENDING_REVIEW',
    current_stage: 'VERIFICATION_REQUIRED',
    progress_pct: 94,
    detected_language: 'en',
    page_count: 2,
    image_quality_score: 0.87,
    overall_confidence: 0.83,
    needs_human_review: true,
    has_anomalies: true,
    is_duplicate: false,
    duplicate_of_id: null,
    error_message: null,
    stage_timings: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:10:00Z',
    completed_at: null,
    extracted_fields: [
      {
        id: 'f1',
        field_name: 'khasra_number',
        field_display: 'Khasra Number',
        raw_value: 'KH-10142',
        normalized_value: 'KH-10142',
        confidence_score: 0.94,
        ocr_confidence: 0.9,
        extraction_method: 'regex',
        source_page: 1,
        validation_status: 'AUTO_VALID',
        validation_message: null,
        needs_review: false,
        verified_by: null,
        verified_value: null,
        verified_at: null,
      },
      {
        id: 'f2',
        field_name: 'mutation_number',
        field_display: 'Mutation Number',
        raw_value: 'MUT-2024-08-1432',
        normalized_value: 'MUT-2024-08-1432',
        confidence_score: 0.55,
        ocr_confidence: 0.6,
        extraction_method: 'regex',
        source_page: 1,
        validation_status: 'AUTO_INVALID',
        validation_message: 'low confidence',
        needs_review: true,
        verified_by: null,
        verified_value: null,
        verified_at: null,
      },
    ],
    anomalies: [
      {
        id: 'a1',
        anomaly_type: 'MISSING_REQUIRED',
        field_name: 'state',
        severity: 'HIGH',
        description: "Required field 'State' could not be extracted from the document.",
        confidence: 0.95,
        resolved: false,
        created_at: '2026-01-01T00:09:00Z',
      },
    ],
    verification_tasks: [],
    ...overrides,
  } as PipelineJobDetail;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/pipeline']}>
      <Routes>
        <Route path="/pipeline" element={<PipelinePage />} />
        <Route path="/intake" element={<div>intake page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PipelinePage with real job data', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [listItem()],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    });
    vi.spyOn(pipelineApi, 'getJob').mockResolvedValue(detail());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('shows the real document and job instead of mock data', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('khasra_nakal_KH-10142.pdf')).toBeInTheDocument();
    });
    // The fictional "Demo mode — using Mock OCR backend" banner must be gone.
    expect(screen.queryByText(/Mock OCR backend/i)).not.toBeInTheDocument();
  });

  it('counts KPIs from the jobs list rather than hardcoding 4/1/1/1/1', async () => {
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [
        listItem({ id: 'a', status: 'completed' }),
        listItem({ id: 'b', status: 'processing' }),
        listItem({ id: 'c', status: 'verification_required' }),
        listItem({ id: 'd', status: 'failed' }),
      ],
      total: 4,
      page: 1,
      page_size: 50,
      pages: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Total Jobs')).toBeInTheDocument();
    });
    // Labels like "Processing" also appear as queue status badges, so read the
    // value out of the matching .kpi tile rather than matching the text globally.
    const kpi = (label: string) => {
      const tile = screen.getAllByText(label).find(el => el.closest('.kpi'));
      return tile?.closest('.kpi')?.querySelector('.kpi__value')?.textContent;
    };
    expect(kpi('Total Jobs')).toBe('4');
    expect(kpi('Processing')).toBe('1');
    expect(kpi('Pending Review')).toBe('1');
    expect(kpi('Completed')).toBe('1');
    expect(kpi('Failed')).toBe('1');
  });

  it('renders the extracted fields returned by the API', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    // The Khasra also shows in the queue row, so scope to the fields table.
    const table = screen.getByText('Khasra Number').closest('table') as HTMLElement;
    expect(within(table).getByText('KH-10142')).toBeInTheDocument();
    expect(within(table).getByText('Mutation Number')).toBeInTheDocument();
    expect(within(table).getByText('94%')).toBeInTheDocument();
    expect(within(table).getByText('AUTO_VALID')).toBeInTheDocument();
  });

  it('shows real job metadata: language, pages and quality', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Language')).toBeInTheDocument();
    });
    // Read each metadata value from the stat block that owns its label.
    const stat = (label: string) => {
      const el = screen.getAllByText(label).find(n => n.closest('.card'));
      return el?.parentElement?.lastElementChild?.textContent;
    };
    expect(stat('Language')).toBe('en');
    expect(stat('Pages')).toBe('2');
    expect(stat('Quality Score')).toBe('87%');
    expect(stat('Overall Confidence')).toBe('83%');
  });

  it('lists real anomalies on the anomalies tab', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /anomalies/i }));

    expect(screen.getByText('MISSING_REQUIRED')).toBeInTheDocument();
    expect(screen.getByText(/Required field 'State' could not be extracted/)).toBeInTheDocument();
  });

  it('persists a verification through the API and refreshes from the server', async () => {
    const verifySpy = vi.spyOn(pipelineApi, 'verifyField').mockResolvedValue({ ok: true });

    renderPage();

    // "Mutation Number" appears in both the review panel and the fields table;
    // wait on the review panel, then act on its Verify button.
    await waitFor(() => {
      expect(screen.getByText('Human Verification Required (1 fields)')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /^verify$/i }));

    const input = await screen.findByPlaceholderText(/enter correct value/i);
    await userEvent.clear(input);
    await userEvent.type(input, 'MUT-9999');
    await userEvent.click(screen.getByRole('button', { name: /confirm/i }));

    // The old page only set local React state and never called the backend.
    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledWith('f2', 'MUT-9999');
    });
    await waitFor(() => {
      expect(pipelineApi.getJob).toHaveBeenCalledTimes(2);
    });
  });

  it('reports a failed job with a working retry that hits the API', async () => {
    const retrySpy = vi.spyOn(pipelineApi, 'retryJob').mockResolvedValue({ id: 'job-1' });
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [listItem({ status: 'failed', stage: 'OCR', stage_status: 'FAILED', failed_stage: 'OCR', error_message: 'Tesseract exited with code 1' })],
      total: 1, page: 1, page_size: 50, pages: 1,
    });
    vi.spyOn(pipelineApi, 'getJob').mockResolvedValue(
      detail({ status: 'FAILED', current_stage: 'OCR', error_message: 'Tesseract exited with code 1' }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Pipeline Failed/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Tesseract exited with code 1/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /retry pipeline/i }));
    await waitFor(() => {
      expect(retrySpy).toHaveBeenCalledWith('job-1');
    });
  });

  it('offers to reprocess a job that is only waiting on verification', async () => {
    // The state a mis-read document lands in. Retry used to be reachable only
    // from the "Pipeline Failed" banner, so a job whose every field came back
    // empty had no way to re-run the OCR from the UI.
    const retrySpy = vi.spyOn(pipelineApi, 'retryJob').mockResolvedValue({ id: 'job-1' });
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [listItem()],
      total: 1, page: 1, page_size: 50, pages: 1,
    });
    vi.spyOn(pipelineApi, 'getJob').mockResolvedValue(detail());

    renderPage();

    const reprocess = await screen.findByRole('button', { name: /reprocess/i });
    await userEvent.click(reprocess);
    await waitFor(() => {
      expect(retrySpy).toHaveBeenCalledWith('job-1');
    });
  });

  it('hides reprocess while the job is still running', async () => {
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [listItem({ status: 'processing', stage: 'OCR', stage_status: 'OCR_RUNNING', progress_pct: 40 })],
      total: 1, page: 1, page_size: 50, pages: 1,
    });
    vi.spyOn(pipelineApi, 'getJob').mockResolvedValue(
      detail({ status: 'OCR_RUNNING', current_stage: 'OCR', progress_pct: 40 }),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/khasra_nakal_KH-10142\.pdf/)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /reprocess/i })).not.toBeInTheDocument();
  });

  it('says so when there are no jobs at all', async () => {    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [], total: 0, page: 1, page_size: 50, pages: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No jobs yet')).toBeInTheDocument();
    });
  });

  it('surfaces a list failure instead of rendering an empty page', async () => {
    vi.spyOn(pipelineApi, 'listJobs').mockRejectedValue(new Error('queue unavailable'));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('queue unavailable')).toBeInTheDocument();
    });
  });

  it('filters the queue by status', async () => {
    vi.spyOn(pipelineApi, 'listJobs').mockResolvedValue({
      items: [
        listItem({ id: 'a', status: 'completed', document_name: 'done.pdf' }),
        listItem({ id: 'b', status: 'failed', document_name: 'broken.pdf' }),
      ],
      total: 2, page: 1, page_size: 50, pages: 1,
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('done.pdf')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByRole('combobox'), 'failed');
    await waitFor(() => {
      expect(screen.queryByText('done.pdf')).not.toBeInTheDocument();
    });
    expect(screen.getByText('broken.pdf')).toBeInTheDocument();
  });
});
