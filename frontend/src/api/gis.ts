/**
 * GIS API — cadastral spatial data.
 *
 * `/gis/records` is what makes an uploaded document visible on the map: the
 * processing pipeline writes a centroid for every land record it touches, and
 * the feature properties carry `from_upload` plus the document it came from, so
 * the map can tell a scanned parcel from a seeded one.
 */
import apiClient from './client';

/** One land record's parcel geometry, as returned by /gis/records. */
export interface GisParcelProperties {
  id: string;
  khasra_number: string;
  owner_name: string;
  district: string;
  state: string;
  village: string;
  area_hectares: number;
  land_use_type: string;
  status: string;
  latitude: number | null;
  longitude: number | null;
  source: string | null;
  /** True when an uploaded document produced this parcel's position. */
  from_upload: boolean;
  document_id: string | null;
  document_name: string | null;
}

export interface GisFeature {
  type: 'Feature';
  id: string;
  /** Polygon for a parcel boundary, Point when only a centroid is known. */
  geometry: {
    type: 'Polygon' | 'Point';
    coordinates: number[][] | number[] | number[][][];
  } | null;
  properties: GisParcelProperties;
}

export interface GisFeatureCollection {
  type: 'FeatureCollection';
  features: GisFeature[];
  total: number;
  /** How many of the returned parcels came from an uploaded document. */
  from_upload: number;
  disclaimer: string;
}

export interface RecordCoordinates {
  record_id: string;
  khasra_number: string;
  coordinates: Array<{
    id: string;
    latitude: number | null;
    longitude: number | null;
    coordinate_type: string;
    geojson: Record<string, unknown> | null;
    source: string | null;
    accuracy_meters: number | null;
  }>;
}

export const gisApi = {
  /**
   * Every record that has a centroid, as a GeoJSON FeatureCollection.
   *
   * `limit` is capped at 2000 server-side; the map does not need more than that
   * to be useful and the payload is a full feature per record.
   */
  listRecords: async (params?: {
    state?: string;
    district?: string;
    land_use?: string;
    limit?: number;
  }): Promise<GisFeatureCollection> => {
    const res = await apiClient.get<GisFeatureCollection>('/gis/records', { params });
    return res.data;
  },

  /** Centroid and boundary rows for one record. */
  getRecordCoordinates: async (recordId: string): Promise<RecordCoordinates> => {
    const res = await apiClient.get<RecordCoordinates>(`/gis/record/${recordId}`);
    return res.data;
  },

  /**
   * Attach a surveyed position to a record.
   *
   * A coordinate set here is a real measurement, so the processing pipeline
   * leaves it alone when the document is re-run.
   */
  setCoordinates: async (
    recordId: string,
    body: { latitude: number; longitude: number; altitude_m?: number; source?: string },
  ) => {
    const res = await apiClient.post(`/gis/record/${recordId}/coordinates`, body);
    return res.data;
  },
};
