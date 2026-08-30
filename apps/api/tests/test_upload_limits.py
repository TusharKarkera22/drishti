import asyncio
import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app import main as main_module
from app.core import store
from app.routers import ingest as ingest_router
from app.routers import intake as intake_router


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


def test_ingest_rejects_too_many_files_before_reading(monkeypatch):
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_FILES", 1)
    files = [_upload("a.csv", b"id\n1\n"), _upload("b.csv", b"id\n2\n")]

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(ingest_router.ingest_files(files=files, name="too many"))

    assert exc_info.value.status_code == 400
    assert "at most 1 file" in exc_info.value.detail


def test_ingest_rejects_unsupported_extension():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[_upload("records.json", b'[{"id": 1}]')],
                name="unsupported",
            )
        )

    assert exc_info.value.status_code == 415
    assert "CSV and XLSX" in exc_info.value.detail


def test_ingest_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_BYTES", 8)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[_upload("records.csv", b"id\n123456789\n")],
                name="oversized",
            )
        )

    assert exc_info.value.status_code == 413
    assert "per-file limit" in exc_info.value.detail


def test_ingest_rejects_request_over_total_byte_limit(monkeypatch):
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_BYTES", 100)
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_TOTAL_BYTES", 12)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[
                    _upload("a.csv", b"id\n1234\n"),
                    _upload("b.csv", b"id\n5678\n"),
                ],
                name="too large together",
            )
        )

    assert exc_info.value.status_code == 413
    assert "request limit" in exc_info.value.detail


def test_ingest_rejects_rows_over_request_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_ROWS", 2)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[_upload("records.csv", b"id\n1\n2\n3\n")],
                name="too many rows",
            )
        )

    assert exc_info.value.status_code == 413
    assert "at most 2 rows" in exc_info.value.detail
    assert list(tmp_path.iterdir()) == []


def test_small_csv_still_ingests(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)

    result = asyncio.run(
        ingest_router.ingest_files(
            files=[_upload("records.csv", b"fir_no,category\nA1,Theft\nA2,Cyber\n")],
            name="small upload",
        )
    )

    assert result["name"] == "small upload"
    assert result["tables"][0]["row_count"] == 2


def test_intake_uses_same_file_size_guard(monkeypatch):
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_BYTES", 8)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            intake_router.clean(
                file=_upload("records.csv", b"id\n123456789\n"),
                name="oversized",
                dest_dataset_id="",
            )
        )

    assert exc_info.value.status_code == 413


def test_append_uses_same_file_size_guard(monkeypatch):
    monkeypatch.setattr(store, "load_manifest", lambda _dataset_id: object())
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_BYTES", 8)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.append_to_dataset(
                "existing",
                files=[_upload("records.csv", b"id\n123456789\n")],
            )
        )

    assert exc_info.value.status_code == 413


def test_ingest_rejects_xlsx_with_excessive_expanded_size(monkeypatch):
    monkeypatch.setattr(ingest_router, "MAX_XLSX_UNCOMPRESSED_BYTES", 64)
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/sharedStrings.xml", "A" * 1024)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[_upload("records.xlsx", payload.getvalue())],
                name="expanded workbook",
            )
        )

    assert exc_info.value.status_code == 413
    assert "expanded size" in exc_info.value.detail


def test_ingest_rejects_aggregate_rows_across_files(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(ingest_router, "MAX_UPLOAD_ROWS", 3)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            ingest_router.ingest_files(
                files=[
                    _upload("a.csv", b"id\n1\n2\n"),
                    _upload("b.csv", b"id\n3\n4\n"),
                ],
                name="too many combined rows",
            )
        )

    assert exc_info.value.status_code == 413
    assert list(tmp_path.iterdir()) == []


def test_intake_success_persists_validated_raw_upload(monkeypatch, tmp_path):
    started: dict[str, object] = {}
    monkeypatch.setattr(intake_router, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        intake_router,
        "_start_job",
        lambda df, **kwargs: started.update(rows=len(df), **kwargs) or kwargs["job_id"],
    )

    result = asyncio.run(
        intake_router.clean(
            file=_upload("records.csv", b"id,value\n1,alpha\n"),
            name="clean upload",
            dest_dataset_id="",
        )
    )

    assert result["rows"] == 1
    assert started["rows"] == 1
    assert (tmp_path / "intake" / result["job_id"] / "raw.csv").read_bytes() == b"id,value\n1,alpha\n"


def test_http_upload_body_limit_runs_before_multipart_parsing(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main_module, "UPLOAD_BODY_LIMIT_BYTES", 128, raising=False)
    client = TestClient(main_module.app)

    response = client.post(
        "/api/ingest",
        files={"files": ("records.csv", b"id\n" + b"1\n" * 128, "text/csv")},
        data={"name": "too large at transport"},
    )

    assert response.status_code == 413
    assert list(tmp_path.iterdir()) == []
