/**
 * Reports page — computed, not written down.
 *
 * Every number on this screen used to be a hardcoded constant, so the page
 * reported 1,247 records and a 94.2% success rate whether or not a single
 * document had ever been uploaded. It now reads the analytics endpoints, which
 * aggregate the same rows the processing pipeline writes, and each tab has to
 * reflect what those endpoints actually returned.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { ReportsPage } from '../pages/ReportsPage';
import { I18nProvider } from '../i18n/useTranslation';
import { analyticsApi, type KpiSnapshot } from '../api/analytics';

const kpis = (over: Partial<KpiSnapshot> = {}): KpiSnapshot => ({
  records: {
    total: 12,
    verified: 6,
    under_review: 3,
    pending: 2,
    rejected: 1,
    verification_rate_pct: 50,
  },
  pipeline: { total_jobs: 9, failed: 1, pending_review: 1, success_rate_pct: 77.8 },
  area: { total_hectares: 145.25 },
  anomalies: { open: 3 },
  documents: {
    total: 9,
    processed: 7,
    processing_rate_pct: 77.8,
    uploaded_last_24h: 4,
    records_from_upload: 9,
  },
  users: { active: 3 },
  as_of: '2026-01-05T00:00:00Z',
  disclaimer: 'Computed from the live database',
  ...over,
});

function mockAll(k: KpiSnapshot = kpis()) {
  vi.spyOn(analyticsApi, 'getKpis').mockResolvedValue(k);
  vi.spyOn(analyticsApi, 'getRecordsByStatus').mockResolvedValue([
    { status: 'VERIFIED', count: 6 },
    { status: 'UNDER_REVIEW', count: 3 },
    { status: 'PENDING', count: 3 },
  ]);
  vi.spyOn(analyticsApi, 'getRecordsByDistrict').mockResolvedValue([
    { district: 'Lucknow', state: 'Uttar Pradesh', count: 8, total_area_ha: 96.4 },
    { district: 'Varanasi', state: 'Uttar Pradesh', count: 4, total_area_ha: 48.85 },
  ]);
  vi.spyOn(analyticsApi, 'getRecordsByState').mockResolvedValue([
    { state: 'Uttar Pradesh', count: 12, verified: 6, total_area_ha: 145.25 },
  ]);
  vi.spyOn(analyticsApi, 'getRecordsByLandUse').mockResolvedValue([
    { land_use: 'AGRICULTURAL', count: 9, total_area_ha: 120.0 },
    { land_use: 'RESIDENTIAL', count: 3, total_area_ha: 25.25 },
  ]);
  vi.spyOn(analyticsApi, 'getProcessingThroughput').mockResolvedValue([
    { date: '2026-01-04', total: 5, completed: 4, failed: 1 },
  ]);
  vi.spyOn(analyticsApi, 'getAreaDistribution').mockResolvedValue([
    { range: '0-1 ha', count: 4 },
    { range: '1-5 ha', count: 8 },
  ]);
  vi.spyOn(analyticsApi, 'getAnomalyTrends').mockResolvedValue([
    { type: 'AREA_MISMATCH', severity: 'HIGH', count: 2 },
    { type: 'MISSING_REQUIRED', severity: 'MEDIUM', count: 1 },
  ]);
  vi.spyOn(analyticsApi, 'getDocumentsSummary').mockResolvedValue({
    by_status: [{ status: 'VALIDATED', count: 7 }, { status: 'PROCESSING', count: 2 }],
    by_type: [{ document_type: 'SURVEY_MAP', count: 6 }, { document_type: 'TITLE_DEED', count: 3 }],
    records_from_upload: 9,
    records_with_anomalies: 3,
  });
  vi.spyOn(analyticsApi, 'getValidationHealth').mockResolvedValue([
    {
      field_name: 'owner_name',
      total: 9,
      auto_valid: 7,
      auto_invalid: 1,
      human_verified: 1,
      human_rejected: 0,
      needs_review: 1,
      accepted: 8,
      rejected: 1,
      pass_rate_pct: 88.9,
    },
  ]);
  vi.spyOn(analyticsApi, 'getFieldAccuracy').mockResolvedValue({
    data: [
      { field_name: 'owner_name', field_display: 'Owner Name', samples: 9, extracted: 9, found_rate_pct: 100, avg_confidence_pct: 93.5, avg_ocr_confidence_pct: 91.2 },
    ],
    overall_confidence_pct: 83,
  });
}

function renderPage() {
  return render(
    <I18nProvider>
      <MemoryRouter><ReportsPage /></MemoryRouter>
    </I18nProvider>,
  );
}

function kpi(title: string): string | undefined {
  const el = screen.getAllByText(title).find(n => n.closest('.kpi'));
  return el?.closest('.kpi')?.querySelector('.kpi__value')?.textContent;
}

describe('ReportsPage with live analytics', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockAll();
  });

  it('takes its headline numbers from the KPIs endpoint', async () => {
    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('12');
    });
    expect(kpi('Verified')).toBe('6');
    expect(kpi('Open Anomalies')).toBe('3');
    expect(kpi('Pending Review')).toBe('1');
    expect(kpi('Jobs Processed')).toBe('9');
  });

  it('reports how many records came from uploads', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/9 from uploads/)).toBeInTheDocument();
    });
  });

  it('breaks documents down by pipeline status on the uploads tab', async () => {
    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('12');
    });
    await userEvent.click(screen.getByRole('button', { name: 'Uploads' }));

    await waitFor(() => {
      expect(screen.getByText('Documents by Pipeline Status')).toBeInTheDocument();
    });
    expect(screen.getByText('Validated')).toBeInTheDocument();
    expect(screen.getByText('Processing')).toBeInTheDocument();
    expect(screen.getByText(/9 uploaded/)).toBeInTheDocument();
    // The record-level upload counts, not just document counts.
    const uploads = screen.getByText('Records created from uploads').closest('.info-row');
    expect(within(uploads as HTMLElement).getByText('9')).toBeInTheDocument();
  });

  it('shows field pass rates and accuracy from the pipeline', async () => {
    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('12');
    });
    await userEvent.click(screen.getByRole('button', { name: 'Validation Stats' }));

    await waitFor(() => {
      expect(screen.getByText('Field Validation Pass Rates')).toBeInTheDocument();
    });
    expect(screen.getByText('1 fields read from uploads')).toBeInTheDocument();
    // Rate and the pass/fail split the pipeline actually recorded.
    expect(screen.getByText(/88\.9% · 8\/9/)).toBeInTheDocument();
    expect(screen.getByText(/overall 83% confidence/)).toBeInTheDocument();
    expect(screen.getByText('Owner Name')).toBeInTheDocument();
  });

  it('derives the anomaly resolution rate from open and total counts', async () => {
    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('12');
    });
    await userEvent.click(screen.getByRole('button', { name: 'Anomaly Trends' }));

    await waitFor(() => {
      expect(screen.getByText('Anomaly Distribution by Type')).toBeInTheDocument();
    });
    // 2 HIGH + 1 MEDIUM = 3 detected, 3 still open -> 0% resolved.
    expect(screen.getByText('Area Mismatch')).toBeInTheDocument();
    expect(screen.getByText(/0% of detected anomalies are resolved/)).toBeInTheDocument();
  });

  it('lists states and districts the database actually contains', async () => {
    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('12');
    });
    await userEvent.click(screen.getByRole('button', { name: 'By State' }));
    await waitFor(() => {
      expect(screen.getByText('Uttar Pradesh')).toBeInTheDocument();
    });
    expect(screen.getByText('50%')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'By District' }));
    await waitFor(() => {
      expect(screen.getByText(/#1 Lucknow/)).toBeInTheDocument();
    });
    expect(screen.getByText(/#2 Varanasi/)).toBeInTheDocument();
  });

  it('shows empty states instead of invented data when nothing is uploaded', async () => {
    mockAll(kpis({
      records: { total: 0, verified: 0, under_review: 0, pending: 0, rejected: 0, verification_rate_pct: 0 },
      pipeline: { total_jobs: 0, failed: 0, pending_review: 0, success_rate_pct: 0 },
      area: { total_hectares: 0 },
      anomalies: { open: 0 },
      documents: {
        total: 0, processed: 0, processing_rate_pct: 0,
        uploaded_last_24h: 0, records_from_upload: 0,
      },
      users: { active: 0 },
    }));
    vi.spyOn(analyticsApi, 'getDocumentsSummary').mockResolvedValue({
      by_status: [], by_type: [], records_from_upload: 0, records_with_anomalies: 0,
    });
    vi.spyOn(analyticsApi, 'getAnomalyTrends').mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(kpi('Total Records')).toBe('0');
    });
    await userEvent.click(screen.getByRole('button', { name: 'Uploads' }));
    await waitFor(() => {
      expect(screen.getByText('Nothing uploaded yet')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: 'Anomaly Trends' }));
    await waitFor(() => {
      expect(screen.getByText('No anomalies detected')).toBeInTheDocument();
    });
  });

  it('surfaces a failed analytics request instead of stale constants', async () => {
    vi.spyOn(analyticsApi, 'getKpis').mockRejectedValue(
      new Error('Request failed with status code 500'),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/500/)).toBeInTheDocument();
    });
  });
});
