/**
 * Documents page — View / Download actions.
 *
 * Both actions were non-functional: "View" navigated away to the land record
 * (showing nothing about the document that was clicked) and "Download" fired an
 * `alert()` with the document id. These tests pin the real behaviour: a details
 * modal with the extracted content, and an authenticated blob download.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { DocumentsPage } from '../pages/DocumentsPage';
import { documentsApi, type DocumentListItem, type DocumentContentResponse } from '../api/documents';

function listItem(overrides: Partial<DocumentListItem> = {}): DocumentListItem {
  return {
    id: 'doc-1',
    land_record_id: 'rec-1',
    document_type: 'TITLE_DEED',
    original_filename: 'deed.png',
    file_size_bytes: 2048,
    mime_type: 'image/png',
    status: 'VALIDATED',
    validation_notes: null,
    created_at: '2026-01-01T00:00:00Z',
    khasra_number: 'KH-10142',
    survey_number: null,
    owner_name: 'Ramesh Prasad',
    uploader_username: 'e2e_officer',
    job_id: 'job-1',
    processing_status: 'completed',
    current_stage: 'COMPLETED',
    stage_message: null,
    progress_pct: 100,
    failed_stage: null,
    error_type: null,
    error_message: null,
    confidence: 78,
    verification_status: 'NOT_REQUIRED',
    needs_human_review: false,
    ...overrides,
  } as DocumentListItem;
}

function content(overrides: Partial<DocumentContentResponse> = {}): DocumentContentResponse {
  return {
    document: {
      id: 'doc-1',
      original_filename: 'deed.png',
      document_type: 'TITLE_DEED',
      file_size_bytes: 2048,
      mime_type: 'image/png',
      status: 'VALIDATED',
      validation_notes: null,
      created_at: '2026-01-01T00:00:00Z',
      file_available: true,
    },
    pipeline_job: {
      document_id: 'doc-1',
      job_id: 'job-1',
      status: 'completed',
      status_detail: 'COMPLETED',
      stage: 'COMPLETED',
      stage_message: null,
      progress_pct: 100,
      failed_stage: null,
      error_type: null,
      error_message: null,
      confidence: 78,
      verification_status: 'NOT_REQUIRED',
      needs_human_review: false,
      has_anomalies: false,
      is_duplicate: false,
      detected_language: 'en',
      page_count: 1,
      document_status: 'VALIDATED',
      message: 'done',
    },
    extracted_fields: [
      {
        id: 'f1',
        field_name: 'khasra_number',
        field_display: 'Khasra Number',
        raw_value: 'KH-10142',
        normalized_value: 'KH-10142',
        confidence_score: 0.78,
        confidence_pct: 78,
        ocr_confidence: 0.9,
        extraction_method: 'regex',
        source_page: 1,
        validation_status: 'AUTO_VALID',
        validation_message: null,
        needs_review: false,
        verified_value: null,
        verified_at: null,
      },
      {
        id: 'f2',
        field_name: 'owner_name',
        field_display: 'Owner Name',
        raw_value: 'ramesh prasad',
        normalized_value: 'Ramesh Prasad',
        confidence_score: 0.44,
        confidence_pct: 44,
        ocr_confidence: 0.6,
        extraction_method: 'regex',
        source_page: 1,
        validation_status: 'AUTO_INVALID',
        validation_message: 'low confidence',
        needs_review: true,
        verified_value: null,
        verified_at: null,
      },
    ],
    raw_ocr_text: 'Khasra Number: KH-10142\nOwner Name: ramesh prasad',
    land_record: {
      id: 'rec-1',
      khasra_number: 'KH-10142',
      owner_name: 'Ramesh Prasad',
      village: 'Rampur',
      district: 'Lucknow',
      state: 'Uttar Pradesh',
      area_hectares: 2.45,
      status: 'ACTIVE',
    },
    ...overrides,
  } as DocumentContentResponse;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/land-records/:id" element={<div>land record detail page</div>} />
        <Route path="/intake" element={<div>intake page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DocumentsPage view and download actions', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(documentsApi, 'list').mockResolvedValue({
      items: [listItem()],
      total: 1,
      page: 1,
      page_size: 50,
      pages: 1,
    });
  });

  it('opens a details modal with the extracted content instead of navigating away', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(content());

    renderPage();

    const viewBtn = await screen.findByTitle('View details');
    await userEvent.click(viewBtn);

    // The extracted field table is the whole point of "View".
    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    expect(screen.getByText('Extracted content (2 fields)')).toBeInTheDocument();
    expect(screen.getAllByText('KH-10142').length).toBeGreaterThan(0);
    // The owner appears in the list row, the extracted field and the linked
    // record, so assert on the modal specifically rather than a global match.
    const modal = document.querySelector('.modal') as HTMLElement;
    expect(within(modal).getByText('Ramesh Prasad')).toBeInTheDocument();
    expect(within(modal).getByText(/Saved to land record/)).toBeInTheDocument();
    // It must NOT have navigated to the land record.
    expect(screen.queryByText('land record detail page')).not.toBeInTheDocument();
  });

  it('shows a review badge for fields that need human review', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(content());

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    await waitFor(() => {
      expect(screen.getByText('needs review')).toBeInTheDocument();
    });
  });

  it('shows the raw OCR reads behind a toggle', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(content());

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    const toggle = await screen.findByRole('button', { name: /Show raw reads/i });
    await userEvent.click(toggle);

    expect(screen.getByText(/Khasra Number: KH-10142/)).toBeInTheDocument();
  });

  it('downloads the original file through the api instead of alerting', async () => {
    const downloadSpy = vi
      .spyOn(documentsApi, 'downloadDocument')
      .mockResolvedValue(undefined);

    renderPage();
    await userEvent.click(await screen.findByTitle('Download'));

    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledWith('doc-1', 'deed.png');
    });
  });

  it('downloads from the details modal too', async () => {
    const downloadSpy = vi
      .spyOn(documentsApi, 'downloadDocument')
      .mockResolvedValue(undefined);
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(content());

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Download original/i })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /Download original/i }));

    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledWith('doc-1', 'deed.png');
    });
  });

  it('explains an unprocessed document instead of showing an empty table', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(
      content({ extracted_fields: [], raw_ocr_text: null, pipeline_job: null }),
    );

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    await waitFor(() => {
      expect(screen.getByText(/has not been processed yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Extracted content/)).not.toBeInTheDocument();
  });

  it('surfaces a load failure inside the modal', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockRejectedValue(
      new Error('nope'),
    );

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    await waitFor(() => {
      expect(screen.getByText('nope')).toBeInTheDocument();
    });
  });

  it('closes the modal on Escape', async () => {
    vi.spyOn(documentsApi, 'documentContent').mockResolvedValue(content());

    renderPage();
    await userEvent.click(await screen.findByTitle('View details'));

    await waitFor(() => {
      expect(screen.getByText('Khasra Number')).toBeInTheDocument();
    });
    await userEvent.keyboard('{Escape}');

    await waitFor(() => {
      expect(screen.queryByText('Khasra Number')).not.toBeInTheDocument();
    });
  });
});
