/**
 * Anomalies page — real findings from real uploads.
 *
 * The page rendered a hardcoded list of eight anomalies, so it could not show
 * (or clear) a single finding produced by an actual upload. It now reads
 * `/pipeline/anomalies/feed`, which joins each anomaly to the document and the
 * land record it came from, and resolving a finding posts to the API.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { AnomaliesPage } from '../pages/AnomaliesPage';
import { pipelineApi, type AnomalyFeedItem } from '../api/pipeline';

function item(overrides: Partial<AnomalyFeedItem> = {}): AnomalyFeedItem {
  return {
    id: 'anom-1',
    job_id: 'job-1',
    document_id: 'doc-1',
    document_name: 'khasra_nakal_KH-10142.pdf',
    document_type: 'SURVEY_MAP',
    land_record_id: 'rec-1',
    khasra_number: 'KH-10142',
    village: 'Rampur',
    district: 'Lucknow',
    anomaly_type: 'AREA_MISMATCH',
    field_name: 'land_area',
    severity: 'HIGH',
    description: "Land area on the deed does not match the cadastral map.",
    confidence: 0.87,
    confidence_pct: 87,
    resolved: false,
    resolved_by: null,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function feed(items: AnomalyFeedItem[]) {
  return { items, total: items.length, page: 1, page_size: 200, pages: 1 };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/anomalies']}>
      <Routes>
        <Route path="/anomalies" element={<AnomaliesPage />} />
        <Route path="/land-records/:id" element={<div>record page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

/** The filter dropdowns repeat every severity and type as an <option>, so
 *  assertions about a row have to be scoped to the table body. */
function log(): HTMLElement {
  return screen.getByRole('table') as HTMLElement;
}

describe('AnomaliesPage with real findings', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(pipelineApi, 'listAnomalies').mockResolvedValue(feed([item()]));
    vi.spyOn(pipelineApi, 'resolveAnomaly').mockResolvedValue({
      id: 'anom-1',
      resolved: true,
    });
  });

  it('shows the uploaded document the finding came from', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('khasra_nakal_KH-10142.pdf')).toBeInTheDocument();
    });
    const row = within(log());
    expect(row.getByText('KH-10142')).toBeInTheDocument();
    expect(row.getByText('Area Mismatch')).toBeInTheDocument();
    expect(row.getByText('HIGH')).toBeInTheDocument();
    expect(row.getByText(/Land area on the deed/)).toBeInTheDocument();
    // The row links to the record the anomaly was written against.
    expect(row.getByText('KH-10142').closest('a')).toHaveAttribute(
      'href',
      '/land-records/rec-1',
    );
  });

  it('renders confidence as a percentage, not the raw 0-1 ratio', async () => {
    renderPage();

    await waitFor(() => {
      expect(within(log()).getByText('87%')).toBeInTheDocument();
    });
    expect(within(log()).queryByText('0.87')).not.toBeInTheDocument();
  });

  it('counts KPIs from the feed rather than hardcoding them', async () => {
    vi.spyOn(pipelineApi, 'listAnomalies').mockResolvedValue(
      feed([
        item({ id: 'a', severity: 'HIGH' }),
        item({ id: 'b', severity: 'HIGH' }),
        item({ id: 'c', severity: 'LOW' }),
        item({ id: 'd', severity: 'LOW', resolved: true }),
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getAllByText('Total Anomalies').length).toBeGreaterThan(0);
    });
    const kpi = (label: string) => {
      const tile = screen.getAllByText(label).find(el => el.closest('.kpi'));
      return tile?.closest('.kpi')?.querySelector('.kpi__value')?.textContent;
    };
    expect(kpi('Total Anomalies')).toBe('4');
    expect(kpi('High Severity')).toBe('2');
    expect(kpi('Open / Unresolved')).toBe('3');
  });

  it('resolving a finding calls the API and marks the row resolved', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Resolve' })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => {
      expect(pipelineApi.resolveAnomaly).toHaveBeenCalledWith('anom-1');
    });
    await waitFor(() => {
      expect(within(log()).getByText('Resolved')).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'Resolve' })).not.toBeInTheDocument();
  });

  it('does not claim success when the resolve call fails', async () => {
    vi.spyOn(pipelineApi, 'resolveAnomaly').mockRejectedValue(
      new Error('Request failed with status code 403'),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Resolve' })).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: 'Resolve' }));

    await waitFor(() => {
      expect(screen.getByText(/403/)).toBeInTheDocument();
    });
    // Still open, because the server refused.
    expect(screen.getByRole('button', { name: 'Resolve' })).toBeInTheDocument();
  });

  it('filters the log by severity', async () => {
    vi.spyOn(pipelineApi, 'listAnomalies').mockResolvedValue(
      feed([
        item({ id: 'a', severity: 'HIGH', description: 'Area mismatch on the deed' }),
        item({ id: 'b', severity: 'LOW', description: 'Low confidence read on owner' }),
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Area mismatch on the deed')).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByDisplayValue('All Severities'), 'LOW');

    await waitFor(() => {
      expect(screen.queryByText('Area mismatch on the deed')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Low confidence read on owner')).toBeInTheDocument();
  });

  it('says so when no upload has been flagged yet', async () => {
    vi.spyOn(pipelineApi, 'listAnomalies').mockResolvedValue(feed([]));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No anomalies to show')).toBeInTheDocument();
    });
  });
});
