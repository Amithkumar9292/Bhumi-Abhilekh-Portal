/**
 * Map page — real parcel coordinates.
 *
 * The page used to draw a decorative grid of hardcoded rectangles with made-up
 * Khasra numbers, so an uploaded document could never appear on it. It now reads
 * `/gis/records`, which the processing pipeline populates with a centroid for
 * every record it touches, and each feature carries the document it came from.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import { MapPage } from '../pages/MapPage';
import { gisApi, type GisFeature } from '../api/gis';

function feature(overrides: Partial<GisFeature['properties']> = {}): GisFeature {
  const properties = {
    id: 'rec-1',
    khasra_number: 'KH-10142',
    owner_name: 'Ramesh Prasad',
    district: 'Lucknow',
    state: 'Uttar Pradesh',
    village: 'Rampur',
    area_hectares: 2.45,
    land_use_type: 'AGRICULTURAL',
    status: 'UNDER_REVIEW',
    latitude: 26.8467,
    longitude: 80.9467,
    source: 'Document scan',
    from_upload: true,
    document_id: 'doc-1',
    document_name: 'khasra_nakal_KH-10142.pdf',
    ...overrides,
  };
  return {
    type: 'Feature',
    id: properties.id,
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [80.94, 26.84], [80.95, 26.84], [80.95, 26.85], [80.94, 26.85], [80.94, 26.84],
      ]],
    },
    properties,
  };
}

function collection(features: GisFeature[]) {
  return {
    type: 'FeatureCollection' as const,
    features,
    total: features.length,
    from_upload: features.filter(f => f.properties.from_upload).length,
    disclaimer: '⚠ Coordinates are SYNTHETIC unless read from the document — demo use only',
  };
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/map']}>
      <Routes>
        <Route path="/map" element={<MapPage />} />
        <Route path="/land-records/:id" element={<div>record page</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('MapPage with real GIS data', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(gisApi, 'listRecords').mockResolvedValue(collection([feature()]));
  });

  it('renders a parcel from the API instead of a mock grid', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('KH-10142')).toBeInTheDocument();
    });
    expect(gisApi.listRecords).toHaveBeenCalled();
    // Two SVG copies of the parcel: the map shape and the sidebar list.
    expect(screen.getAllByText('KH-10142').length).toBeGreaterThan(0);
  });

  it('names the uploaded document that produced the parcel', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/1 from uploaded document/)).toBeInTheDocument();
    });
    await userEvent.click(screen.getAllByText('KH-10142')[0]);

    await waitFor(() => {
      expect(screen.getByText('From upload:')).toBeInTheDocument();
    });
    expect(
      screen.getByText('khasra_nakal_KH-10142.pdf'),
    ).toBeInTheDocument();
  });

  it('tells a seeded parcel apart from an uploaded one', async () => {
    vi.spyOn(gisApi, 'listRecords').mockResolvedValue(
      collection([
        feature({ id: 'rec-1', from_upload: false, document_id: null, document_name: null, source: 'Seed data' }),
        feature({
          id: 'rec-2',
          khasra_number: 'KH-20001',
          owner_name: 'Sunita Devi',
          from_upload: true,
          document_id: 'doc-2',
          document_name: 'khasra_nakal_KH-20001.pdf',
        }),
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('KH-20001')).toBeInTheDocument();
    });
    // Click the seeded parcel: it must not claim an upload.
    const seeded = screen.getAllByText('KH-10142')[0];
    await userEvent.click(seeded);

    await waitFor(() => {
      expect(screen.getByText(/No uploaded document linked/)).toBeInTheDocument();
    });
  });

  it('can hide parcels that did not come from an upload', async () => {
    vi.spyOn(gisApi, 'listRecords').mockResolvedValue(
      collection([
        feature({ id: 'rec-1', from_upload: false, document_id: null, document_name: null }),
        feature({ id: 'rec-2', khasra_number: 'KH-20001', owner_name: 'Sunita Devi' }),
      ]),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('KH-10142')).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole('button', { name: /uploaded only/i }));

    await waitFor(() => {
      expect(screen.queryByText('KH-10142')).not.toBeInTheDocument();
    });
    expect(screen.getByText('KH-20001')).toBeInTheDocument();
  });

  it('surfaces an API failure instead of showing an empty map', async () => {
    vi.spyOn(gisApi, 'listRecords').mockRejectedValue(
      new Error('Request failed with status code 500'),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/500/)).toBeInTheDocument();
    });
  });
});
