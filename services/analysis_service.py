import mimetypes
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import ExifTags, Image, UnidentifiedImageError

from infrastructure.audit import utc_now
from infrastructure.repositories import JsonlWriter
from services.case_service import CaseService


@dataclass
class AnalysisResult:
    result_id: str
    analysis_type: str
    status: str
    source_path: str
    created_at: str
    data: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class AnalysisService:
    SIGNATURES = (
        ("PNG", b"\x89PNG\r\n\x1a\n", {".png"}),
        ("JPEG", b"\xff\xd8\xff", {".jpg", ".jpeg", ".jpe"}),
        ("GIF", (b"GIF87a", b"GIF89a"), {".gif"}),
        ("PDF", b"%PDF-", {".pdf"}),
        ("ZIP", b"PK\x03\x04", {".zip", ".jar", ".docx", ".xlsx", ".pptx"}),
    )
    EXTENSIONS = {
        "PNG": {".png"}, "JPEG": {".jpg", ".jpeg", ".jpe"}, "GIF": {".gif"},
        "PDF": {".pdf"}, "ZIP": {".zip", ".jar", ".docx", ".xlsx", ".pptx"},
        "TEXT": {".txt", ".log", ".csv", ".md", ".json", ".xml", ".ini", ".py"},
    }

    def __init__(self, cases: CaseService):
        self.cases = cases

    def identify_type(self, path: Path) -> AnalysisResult:
        try:
            with path.open("rb") as handle:
                header = handle.read(16)
            detected = "UNKNOWN"
            for name, signature, _ in self.SIGNATURES:
                signatures = signature if isinstance(signature, tuple) else (signature,)
                if any(header.startswith(item) for item in signatures):
                    detected = name
                    break
            if detected == "UNKNOWN" and self._is_text(path):
                detected = "TEXT"
            extension = path.suffix.casefold()
            expected = self.EXTENSIONS.get(detected, set())
            mismatch = bool(extension and detected not in {"UNKNOWN", "TEXT"} and extension not in expected)
            return self._result("file_type", path, {
                "detected_type": detected,
                "extension": extension,
                "extension_mismatch": mismatch,
                "mime_type": mimetypes.guess_type(path.name)[0],
            }, ["Extension mismatch is not evidence of malicious behavior"] if mismatch else [])
        except (OSError, ValueError) as exc:
            return self._error("file_type", path, str(exc))

    def search_text(self, paths: list[Path], keyword: str, case_sensitive: bool = False) -> AnalysisResult:
        if not keyword:
            raise ValueError("keyword must not be empty")
        matches = []
        needle = keyword if case_sensitive else keyword.casefold()
        for path in paths:
            try:
                kind = self.identify_type(path).data["detected_type"]
                if kind != "TEXT":
                    continue
                with path.open("r", encoding="utf-8", errors="strict") as handle:
                    for line_number, line in enumerate(handle, 1):
                        haystack = line if case_sensitive else line.casefold()
                        if needle in haystack:
                            matches.append({
                                "path": str(path), "line": line_number,
                                "summary": line.strip()[:500],
                            })
            except (OSError, UnicodeError):
                continue
        result = self._result("keyword_search", Path("<multiple>"), {
            "keyword": keyword, "case_sensitive": case_sensitive,
            "match_count": len(matches), "matches": matches,
        })
        self._persist(result)
        return result

    def extract_metadata(self, path: Path) -> AnalysisResult:
        try:
            with Image.open(path) as image:
                exif = image.getexif()
                fields = {}
                for tag, value in exif.items():
                    name = ExifTags.TAGS.get(tag, str(tag))
                    if isinstance(value, bytes):
                        value = value.decode("utf-8", errors="replace")
                    fields[name] = value
                data = {
                    "format": image.format, "width": image.width, "height": image.height,
                    "exif": fields, "capture_time": fields.get("DateTimeOriginal"),
                    "device_model": fields.get("Model"), "orientation": fields.get("Orientation"),
                }
            return self._result("image_metadata", path, data)
        except (OSError, UnidentifiedImageError) as exc:
            return self._error("image_metadata", path, str(exc))

    def create_thumbnail(self, source: Path, size: tuple[int, int] = (320, 320)) -> Path:
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before creating a thumbnail")
        output = self.cases.case_path(case.case_id) / "thumbnails" / f"{uuid.uuid4()}.jpg"
        try:
            with Image.open(source) as image:
                image.thumbnail(size)
                output.parent.mkdir(parents=True, exist_ok=True)
                image.convert("RGB").save(output, "JPEG", quality=85)
        except (OSError, UnidentifiedImageError):
            output.unlink(missing_ok=True)
            raise
        self.cases.audit.append("local-user", "analysis.thumbnail_created", "file", str(source), {}, {"status": "success", "path": str(output)})
        return output

    def set_annotation(self, entry_id: str, label: str, note: str) -> dict:
        if label not in {"important", "suspicious", "to_analyze"}:
            raise ValueError("unsupported annotation label")
        case = self.cases.active_case
        if case is None:
            raise RuntimeError("open a case before annotating files")
        record = {"annotation_id": str(uuid.uuid4()), "entry_id": entry_id, "label": label, "note": note, "actor": "local-user", "created_at": utc_now()}
        JsonlWriter(self.cases.case_path(case.case_id) / "annotations.jsonl").append(record)
        self.cases.audit.append("local-user", "file.annotation_added", "file", entry_id, {"label": label}, {"status": "success"})
        return record

    def _is_text(self, path: Path) -> bool:
        try:
            sample = path.read_bytes()[:8192]
            if b"\x00" in sample:
                return False
            sample.decode("utf-8")
            return True
        except (OSError, UnicodeError):
            return False

    def _result(self, analysis_type: str, path: Path, data: dict, warnings=None) -> AnalysisResult:
        result = AnalysisResult(str(uuid.uuid4()), analysis_type, "succeeded", str(path), utc_now(), data, warnings or [])
        self._persist(result)
        return result

    def _error(self, analysis_type: str, path: Path, error: str) -> AnalysisResult:
        result = AnalysisResult(str(uuid.uuid4()), analysis_type, "failed", str(path), utc_now(), error=error)
        self._persist(result)
        return result

    def _persist(self, result: AnalysisResult) -> None:
        case = self.cases.active_case
        if case is None:
            return
        JsonlWriter(self.cases.case_path(case.case_id) / "analysis_results.jsonl").append(asdict(result))
