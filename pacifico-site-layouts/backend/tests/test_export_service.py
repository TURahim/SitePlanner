import io
from uuid import UUID

import pytest

from app.services import export_service


class DummyS3Service:
    """Minimal async S3 stub for export service tests."""

    def __init__(self):
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload_output_file(self, s3_key: str, content: bytes, content_type: str, metadata=None):
        self.uploads.append((s3_key, content, content_type))
        return s3_key

    async def get_output_presigned_url(self, s3_key: str, expires_in: int = 3600) -> str:
        return f"https://example.com/{s3_key}"

    # Some export paths call upload_json instead of upload_output_file.
    async def upload_json(self, s3_key: str, data: dict):
        payload = io.StringIO()
        payload.write(str(data))
        self.uploads.append((s3_key, payload.getvalue().encode("utf-8"), "application/json"))
        return s3_key


@pytest.fixture
def dummy_s3(monkeypatch):
    """Provide a fresh dummy S3 service for each test."""
    service = DummyS3Service()
    monkeypatch.setattr(export_service, "get_s3_service", lambda: service)
    # Ensure the module-level singleton does not retain a previous real instance.
    monkeypatch.setattr(export_service, "_export_service", None)
    return service


@pytest.mark.asyncio
async def test_export_pdf_handles_none_values(monkeypatch, dummy_s3):
    monkeypatch.setattr(export_service, "_export_service", None)
    svc = export_service.ExportService()

    layout_id = UUID("123e4567-e89b-12d3-a456-426614174000")
    layout_data = {
        "total_capacity_kw": None,
        "cut_volume_m3": None,
        "fill_volume_m3": None,
        "terrain_processed": True,
    }
    assets = [
        {
            "id": "asset-1",
            "asset_type": "solar_array",
            "name": "Array 1",
            "capacity_kw": None,
            "elevation_m": None,
            "slope_deg": 4.2,
            "position": {"type": "Point", "coordinates": [-122.0, 37.0]},
        }
    ]
    roads = [
        {
            "id": "road-1",
            "name": "Road 1",
            "length_m": None,
            "max_grade_pct": None,
            "geometry": {"type": "LineString", "coordinates": [[-122.0, 37.0], [-122.1, 37.1]]},
        }
    ]
    terrain_summary = {
        "dem_source": "USGS",
        "dem_resolution_m": 10,
        "elevation": {"min_m": None, "max_m": 1200.5, "range_m": None, "mean_m": None},
        "slope": {
            "min_deg": None,
            "max_deg": 8.4,
            "mean_deg": None,
            "distribution": [{"range": "0-5°", "percentage": None, "area_m2": None}],
        },
        "buildable_area": [
            {"asset_type": "solar_array", "max_slope_deg": 10, "area_ha": None, "percentage": None}
        ],
    }

    url = await svc.export_pdf(
        layout_id=layout_id,
        site_name="Test Site",
        site_area_m2=0,
        layout_data=layout_data,
        assets=assets,
        roads=roads,
        terrain_summary=terrain_summary,
    )

    assert url == f"https://example.com/outputs/{layout_id}/report.pdf"
    # Ensure the PDF was "uploaded" even with None values in the payload.
    assert dummy_s3.uploads
    uploaded_key, _, content_type = dummy_s3.uploads[0]
    assert uploaded_key == f"outputs/{layout_id}/report.pdf"
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_export_csv_handles_missing_numbers(dummy_s3, monkeypatch):
    monkeypatch.setattr(export_service, "_export_service", None)
    svc = export_service.ExportService()
    layout_id = UUID("123e4567-e89b-12d3-a456-426614174001")
    layout_data = {
        "total_capacity_kw": None,
        "cut_volume_m3": None,
        "fill_volume_m3": None,
    }
    assets = [
        {
            "id": "asset-1",
            "name": "Array",
            "asset_type": "solar_array",
            "capacity_kw": None,
            "position": {"type": "Point", "coordinates": [-122.1, 37.1]},
        }
    ]
    roads = [
        {
            "id": "road-1",
            "name": "Road 1",
            "length_m": None,
            "max_grade_pct": None,
            "geometry": {"type": "LineString", "coordinates": [[-122.1, 37.1], [-122.2, 37.2]]},
        }
    ]

    url = await svc.export_csv(
        layout_id=layout_id,
        site_name="Test Site",
        site_area_m2=0,
        layout_data=layout_data,
        assets=assets,
        roads=roads,
    )

    assert url == f"https://example.com/outputs/{layout_id}/layout_data.zip"
    uploaded_key, _, content_type = dummy_s3.uploads[-1]
    assert uploaded_key == f"outputs/{layout_id}/layout_data.zip"
    assert content_type == "application/zip"

