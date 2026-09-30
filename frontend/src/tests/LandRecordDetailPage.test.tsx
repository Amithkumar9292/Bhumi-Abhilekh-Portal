/**
 * Regression tests for the confirm -> record navigation path.
 *
 * The detail page used to look the id up in a hardcoded mock array, so any
 * record actually created by confirming an upload rendered "Record Not Found"
 * even though the record existed in the database. These tests pin the real
 * behaviour: fetch by id, and persist verification decisions.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LandRecordDetailPage } from '../pages/LandRecordDetailPage';
import { landRecordsApi } from '../api/landRecords';
import { useAuthStore } from '../store/authStore';
import type { LandRecord } from '../types/land';

const RECORD_ID = 'e420ec17-2842-494f-b1b9-be897d0b58e1';

function record(overrides: Partial<LandRecord> = {}): LandRecord {
  return {
    id: RECORD_ID,
    khasra_number: '124/3A',
    khatauni_number: '456',
    survey_number: '124/3A',
    state: 'Karnataka',
    district: 'Udupi',
    tehsil: 'Udupi',
    village: 'Brahmavara',
    pin_code: '576213',
    area_hectares: 0.32,
    land_use_type: 'AGRICULTURAL',
    owner_name: 'Ramesh Kumar Naik',
    father_name: 'Suresh Naik',
    address: null,
    aadhaar_last4: null,
    geometry: null,
    status: 'UNDER_REVIEW',
    rejection_reason: null,
    created_by: '7294c3d6-3365-40a0-a9e4-c4f56ea0bb55',
    verified_by: null,
    verified_at: null,
    created_at: '2026-09-30T07:06:53.157726Z',
    updated_at: '2026-09-30T07:57:46.535978Z',
    ...overrides,
  } as LandRecord;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={[`/land-records/${RECORD_ID}`]}>
      <Routes>
        <Route path="/land-records/:id" element={<LandRecordDetailPage />} />
        <Route path="/land-records" element={<div>land records list</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('LandRecordDetailPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: 'u1', role: 'VERIFIER', username: 'verifier' } as never,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('loads a record straight from the API rather than a mock list', async () => {
    const get = vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record());

    renderPage();

    // The exact id returned by confirm must be what we ask the API for.
    await waitFor(() => expect(get).toHaveBeenCalledWith(RECORD_ID));
    expect(await screen.findByText('Ramesh Kumar Naik')).toBeInTheDocument();
    expect(await screen.findByText('Brahmavara')).toBeInTheDocument();
    expect(screen.queryByText(/does not exist/i)).not.toBeInTheDocument();
  });

  it('shows the not-found state when the API returns 404', async () => {
    vi.spyOn(landRecordsApi, 'get').mockRejectedValue({
      response: { status: 404, data: { detail: 'Land record not found.' } },
    });

    renderPage();

    expect(await screen.findByText(/Land record not found\./i)).toBeInTheDocument();
  });

  it('surfaces the server message instead of a generic failure', async () => {
    vi.spyOn(landRecordsApi, 'get').mockRejectedValue({
      response: { status: 500, data: { detail: 'Database unavailable' } },
    });

    renderPage();

    expect(await screen.findByText(/Database unavailable/i)).toBeInTheDocument();
  });

  it('offers Approve for an UNDER_REVIEW record, not just PENDING', async () => {
    // The backend accepts PENDING *or* UNDER_REVIEW; the old gate only matched
    // PENDING, so a freshly confirmed record could never be approved.
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ status: 'UNDER_REVIEW' }));

    renderPage();

    expect(await screen.findByRole('button', { name: /approve/i })).toBeInTheDocument();
  });

  it('hides Approve once the record is already verified', async () => {
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ status: 'VERIFIED' }));

    renderPage();

    await screen.findByText('Ramesh Kumar Naik');
    expect(screen.queryByRole('button', { name: /approve/i })).not.toBeInTheDocument();
  });

  it('persists an approval and shows the status the server returns', async () => {
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ status: 'UNDER_REVIEW' }));
    const verify = vi.spyOn(landRecordsApi, 'verify').mockResolvedValue(
      record({ status: 'VERIFIED', verified_at: '2026-09-30T09:00:00Z', verified_by: 'u1' }),
    );

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /approve/i }));

    await waitFor(() =>
      expect(verify).toHaveBeenCalledWith(RECORD_ID, { approved: true, rejection_reason: undefined }),
    );
    // Status must come from the server response, not optimistic local state.
    // The "Verified" timeline entry only renders when verified_at is set, so it
    // proves the whole server payload was adopted.
    expect(await screen.findByText('by u1')).toBeInTheDocument();
  });

  it('persists a rejection together with its reason', async () => {
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ status: 'UNDER_REVIEW' }));
    const verify = vi.spyOn(landRecordsApi, 'verify').mockResolvedValue(
      record({ status: 'REJECTED', rejection_reason: 'Khasra mismatch' }),
    );

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /reject/i }));
    await userEvent.type(screen.getByPlaceholderText(/specific reason/i), 'Khasra mismatch');
    await userEvent.click(screen.getByRole('button', { name: /confirm rejection/i }));

    await waitFor(() =>
      expect(verify).toHaveBeenCalledWith(RECORD_ID, { approved: false, rejection_reason: 'Khasra mismatch' }),
    );
    expect(await screen.findByText(/Khasra mismatch/)).toBeInTheDocument();
  });

  it('shows an inline error and does not claim success when verification fails', async () => {
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ status: 'UNDER_REVIEW' }));
    vi.spyOn(landRecordsApi, 'verify').mockRejectedValue({
      response: { status: 403, data: { detail: 'Only a verifier can approve records.' } },
    });

    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /approve/i }));

    expect(await screen.findByText(/Only a verifier can approve records\./i)).toBeInTheDocument();
    expect(screen.queryByText(/marked as Verified/i)).not.toBeInTheDocument();
  });

  it('does not render a masked Aadhaar value when none was captured', async () => {
    vi.spyOn(landRecordsApi, 'get').mockResolvedValue(record({ aadhaar_last4: null }));

    renderPage();

    await screen.findByText('Ramesh Kumar Naik');
    expect(screen.queryByText(/••••null/)).not.toBeInTheDocument();
  });
});
