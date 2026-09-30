"""
An uploaded scan has to end up on the map, and be traceable back to the file.

`_sync_gis_coordinate` runs after VALIDATION: it reads a coordinate off the OCR
text if the document prints one, otherwise it places the parcel at a
deterministic point derived from Khasra + district. `GET /gis/records` then has
to say which of its parcels came from an upload and which file produced it,
otherwise the operator sees a polygon with no provenance.

The surveyed-coordinate test is the important one: a DGPS / Bhuvan fix is a real
measurement and must not be replaced by anything read off a scan.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.extended import CoordinateType, GISCoordinate
from app.models.land_record import LandRecord, LandUseType
from app.models.pipeline import ProcessingJob, ProcessingStatus
from app.services.document_processor import (
    SOURCE_DERIVED,
    SOURCE_FROM_SCAN,
    _sync_gis_coordinate,
)
from app.services.gis_service import extract_document_coordinates


# -- coordinate parsing (pure function) ---------------------------------------

class TestExtractDocumentCoordinates:
    def test_reads_labelled_decimal_degrees(self):
        assert extract_document_coordinates(
            "Latitude: 26.8467\nLongitude: 80.9467"
        ) == (26.8467, 80.9467)

    def test_reads_dms_with_hemisphere(self):
        parsed = extract_document_coordinates(
            "LAT 26°50'48\"N  LNG 80°56'48\"E"
        )
        assert parsed is not None
        lat, lng = parsed
        assert lat == pytest.approx(26.8467, abs=1e-3)
        assert lng == pytest.approx(80.9467, abs=1e-3)

    def test_reads_unlabelled_pair(self):
        assert extract_document_coordinates("Pinned at 26.8467, 80.9467 on survey") == (
            26.8467,
            80.9467,
        )

    def test_returns_none_when_there_is_no_coordinate(self):
        assert extract_document_coordinates("Khasra 10142, area 2.45 ha") is None

    def test_rejects_coordinate_outside_india(self):
        """A lat/lng pair far outside India is a different country's registry,
        not a bad OCR read -- placing it would put the parcel in the ocean."""
        assert extract_document_coordinates("Latitude: 48.8566 Longitude: 2.3522") is None

    def test_empty_text_is_not_an_error(self):
        assert extract_document_coordinates("") is None


# -- placement after validation ------------------------------------------------

@pytest_asyncio.fixture
async def record(test_db: AsyncSession) -> LandRecord:
    rec = LandRecord(
        id=uuid.uuid4(),
        khasra_number="KH-10142",
        state="Uttar Pradesh",
        district="Lucknow",
        tehsil="Sadar",
        village="Rampur",
        owner_name="Ramesh Prasad",
        area_hectares=2.45,
        land_use_type=LandUseType.AGRICULTURAL,
    )
    test_db.add(rec)
    await test_db.flush()
    return rec


@pytest_asyncio.fixture
async def job(record: LandRecord) -> ProcessingJob:
    return ProcessingJob(
        id=uuid.uuid4(),
        land_record_id=record.id,
        document_id=uuid.uuid4(),
        status=ProcessingStatus.COMPLETED,
        current_stage="VALIDATION",
    )


async def _centroid(db: AsyncSession, record: LandRecord) -> GISCoordinate | None:
    return (
        await db.execute(
            select(GISCoordinate).where(
                GISCoordinate.land_record_id == record.id,
                GISCoordinate.coordinate_type == CoordinateType.CENTROID,
            )
        )
    ).scalars().first()


class TestSyncGisCoordinate:
    async def test_places_parcel_at_the_printed_coordinate(
        self, test_db: AsyncSession, record: LandRecord, job: ProcessingJob
    ):
        summary = await _sync_gis_coordinate(
            job, test_db, "Latitude: 26.8467\nLongitude: 80.9467"
        )

        assert summary["placed"] is True
        assert summary["source"] == SOURCE_FROM_SCAN
        assert summary["from_document"] is True
        assert summary["latitude"] == pytest.approx(26.8467)

        coord = await _centroid(test_db, record)
        assert coord is not None
        assert coord.latitude == pytest.approx(26.8467)
        assert coord.longitude == pytest.approx(80.9467)
        assert coord.source == SOURCE_FROM_SCAN
        # A polygon, not a bare point, so the parcel has visible area.
        assert coord.geojson is not None
        assert coord.geojson["geometry"]["type"] == "Polygon"
        assert record.geometry == coord.geojson

    async def test_falls_back_to_a_derived_position_and_stays_stable(
        self, test_db: AsyncSession, record: LandRecord, job: ProcessingJob
    ):
        """Most scans print no coordinate. The parcel still has to appear, and
        a retried job must not move it."""
        first = await _sync_gis_coordinate(job, test_db, "Khasra 10142, area 2.45 ha")
        assert first["placed"] is True
        assert first["source"] == SOURCE_DERIVED
        assert first["from_document"] is False

        second = await _sync_gis_coordinate(job, test_db, "Khasra 10142, area 2.45 ha")
        assert (second["latitude"], second["longitude"]) == (
            first["latitude"],
            first["longitude"],
        )

        # Re-running replaces the derived position rather than stacking copies.
        coords = (
            await test_db.execute(
                select(GISCoordinate).where(
                    GISCoordinate.land_record_id == record.id,
                    GISCoordinate.coordinate_type == CoordinateType.CENTROID,
                )
            )
        ).scalars().all()
        assert len(coords) == 1

    async def test_surveyed_coordinate_is_never_overwritten(
        self, test_db: AsyncSession, record: LandRecord, job: ProcessingJob
    ):
        surveyed = GISCoordinate(
            land_record_id=record.id,
            latitude=26.9124,
            longitude=80.9467,
            coordinate_type=CoordinateType.CENTROID,
            source="DGPS survey",
            datum="WGS84",
        )
        test_db.add(surveyed)
        record.geometry = {"type": "Polygon", "coordinates": [[[0, 0]]]}
        await test_db.flush()

        summary = await _sync_gis_coordinate(job, test_db, "Latitude: 26.8467")

        assert summary["placed"] is False
        assert summary["kept_existing"] is True
        assert summary["source"] == "DGPS survey"

        await test_db.refresh(surveyed)
        assert surveyed.latitude == pytest.approx(26.9124)
        assert surveyed.source == "DGPS survey"
        assert record.geometry == {"type": "Polygon", "coordinates": [[[0, 0]]]}

    async def test_no_record_means_no_coordinate(self, test_db: AsyncSession):
        orphan = ProcessingJob(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            land_record_id=None,
            status=ProcessingStatus.COMPLETED,
        )
        summary = await _sync_gis_coordinate(orphan, test_db, "Latitude: 26.8467")
        assert summary == {"land_record_id": None, "placed": False, "source": None}

    async def test_draft_too_small_to_see_is_grown_to_a_visible_polygon(
        self, test_db: AsyncSession, record: LandRecord, job: ProcessingJob
    ):
        """Intake seeds a 0.0001 ha draft area. A 2 m dot is invisible on the map."""
        record.area_hectares = 0.0001
        await test_db.flush()

        await _sync_gis_coordinate(job, test_db, "Latitude: 26.8467")

        coord = await _centroid(test_db, record)
        assert coord is not None
        assert coord.geojson is not None
        ring = coord.geojson["geometry"]["coordinates"][0]
        assert ring[0] != ring[1]


# -- provenance on the map endpoint -------------------------------------------

class TestGisRecordsProvenance:
    async def _uploaded_record(self, db: AsyncSession) -> tuple[ProcessingJob, Document, LandRecord]:
        record = LandRecord(
            id=uuid.uuid4(),
            khasra_number="KH-20001",
            state="Uttar Pradesh",
            district="Lucknow",
            tehsil="Sadar",
            village="Rampur",
            owner_name="Sunita Devi",
            area_hectares=1.2,
            land_use_type=LandUseType.AGRICULTURAL,
        )
        db.add(record)
        await db.flush()

        doc = Document(
            id=uuid.uuid4(),
            land_record_id=record.id,
            document_type=DocumentType.SURVEY_MAP,
            original_filename="khasra_nakal_KH-20001.pdf",
            stored_path=f"uploads/{record.id}/cafe.pdf",
            file_size_bytes=2048,
            mime_type="application/pdf",
            status=DocumentStatus.VALIDATED,
        )
        db.add(doc)
        await db.flush()

        job = ProcessingJob(
            id=uuid.uuid4(),
            document_id=doc.id,
            land_record_id=record.id,
            status=ProcessingStatus.COMPLETED,
            current_stage="COMPLETED",
            progress_pct=100,
        )
        db.add(job)
        db.add(GISCoordinate(
            land_record_id=record.id,
            latitude=26.8467,
            longitude=80.9467,
            coordinate_type=CoordinateType.CENTROID,
            source=SOURCE_FROM_SCAN,
            datum="WGS84",
        ))
        await db.flush()
        return job, doc, record

    async def test_parcel_says_which_upload_produced_it(
        self, async_client: AsyncClient, officer_token: str, test_db: AsyncSession
    ):
        job, doc, record = await self._uploaded_record(test_db)

        r = await async_client.get(
            "/api/v1/gis/records",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        props = next(
            f["properties"] for f in r.json()["features"]
            if f["properties"]["id"] == str(record.id)
        )
        assert props["from_upload"] is True
        assert props["document_id"] == str(doc.id)
        assert props["document_name"] == "khasra_nakal_KH-20001.pdf"

    async def test_seeded_parcel_is_not_labelled_as_an_upload(
        self, async_client: AsyncClient, officer_token: str, test_db: AsyncSession
    ):
        record = LandRecord(
            id=uuid.uuid4(),
            khasra_number="KH-30001",
            state="Uttar Pradesh",
            district="Lucknow",
            tehsil="Sadar",
            village="Rampur",
            owner_name="Demo Owner",
            area_hectares=0.8,
            land_use_type=LandUseType.AGRICULTURAL,
        )
        test_db.add(record)
        await test_db.flush()
        test_db.add(GISCoordinate(
            land_record_id=record.id,
            latitude=26.9000,
            longitude=80.9000,
            coordinate_type=CoordinateType.CENTROID,
            source="Seed data",
            datum="WGS84",
        ))
        await test_db.flush()

        r = await async_client.get(
            "/api/v1/gis/records",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert r.status_code == 200
        props = next(
            f["properties"] for f in r.json()["features"]
            if f["properties"]["id"] == str(record.id)
        )
        assert props["from_upload"] is False
        assert props["document_name"] is None
