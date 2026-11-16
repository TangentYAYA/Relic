import hashlib
from pathlib import Path

from PIL import Image

from services.analysis_service import AnalysisService
from services.case_service import CaseService


def make_service(tmp_path: Path) -> AnalysisService:
    cases = CaseService(tmp_path / "cases")
    cases.create_case("CASE-A", "Analysis", "Tester", "fixture", "analysis")
    return AnalysisService(cases)


def test_signature_and_extension_anomaly(tmp_path):
    service = make_service(tmp_path)
    jpeg = tmp_path / "disguised.txt"
    Image.new("RGB", (4, 3), "red").save(jpeg, "JPEG")
    result = service.identify_type(jpeg)
    assert result.status == "succeeded"
    assert result.data["detected_type"] == "JPEG"
    assert result.data["extension_mismatch"] is True
    assert result.warnings


def test_common_signatures_and_text(tmp_path):
    service = make_service(tmp_path)
    samples = {
        "image.png": b"\x89PNG\r\n\x1a\nrest",
        "image.gif": b"GIF89arest",
        "document.pdf": b"%PDF-1.7\n",
        "archive.zip": b"PK\x03\x04rest",
        "notes.txt": b"plain UTF-8 text",
    }
    for name, content in samples.items():
        path = tmp_path / name
        path.write_bytes(content)
        expected = "TEXT" if name.endswith(".txt") else name.split(".")[1].upper()
        assert service.identify_type(path).data["detected_type"] == expected


def test_search_skips_binary_and_persists_results(tmp_path):
    service = make_service(tmp_path)
    text = tmp_path / "notes.txt"
    text.write_text("Evidence needle\nother\nneedle again", encoding="utf-8")
    binary = tmp_path / "data.bin"
    binary.write_bytes(b"\x00needle\xff")
    result = service.search_text([text, binary], "needle")
    assert result.data["match_count"] == 2
    assert all(match["path"] == str(text) for match in result.data["matches"])
    persisted = next((tmp_path / "cases").glob("*/analysis_results.jsonl")).read_text()
    assert result.result_id in persisted


def test_exif_and_empty_exif(tmp_path):
    service = make_service(tmp_path)
    image = tmp_path / "photo.jpg"
    exif = Image.Exif()
    exif[36867] = "2024:01:02 03:04:05"
    exif[272] = "Relic Camera"
    exif[274] = 6
    Image.new("RGB", (8, 5), "blue").save(image, "JPEG", exif=exif)
    result = service.extract_metadata(image)
    assert result.data["capture_time"] == "2024:01:02 03:04:05"
    assert result.data["device_model"] == "Relic Camera"
    assert result.data["orientation"] == 6
    assert result.data["width"] == 8 and result.data["height"] == 5

    empty = tmp_path / "empty.jpg"
    Image.new("RGB", (2, 2), "white").save(empty, "JPEG")
    empty_result = service.extract_metadata(empty)
    assert empty_result.status == "succeeded"
    assert empty_result.data["exif"] == {}
    assert empty_result.data["capture_time"] is None


def test_annotations_thumbnail_and_error(tmp_path):
    service = make_service(tmp_path)
    image = tmp_path / "photo.png"
    Image.new("RGBA", (20, 10), (1, 2, 3, 255)).save(image)
    annotation = service.set_annotation("inode-3", "suspicious", "review")
    assert annotation["label"] == "suspicious"
    case_dir = next((tmp_path / "cases").glob("*/case.json")).parent
    assert annotation["annotation_id"] in (case_dir / "annotations.jsonl").read_text()
    thumbnail = service.create_thumbnail(image)
    assert thumbnail.is_file()
    with Image.open(thumbnail) as generated:
        assert generated.width <= 320 and generated.height <= 320
    error = service.identify_type(tmp_path / "missing.bin")
    assert error.status == "failed"
