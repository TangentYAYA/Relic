import uuid
from pathlib import Path

from domain.models import Case
from infrastructure.audit import AuditWriter, utc_now
from infrastructure.repositories import JsonRepository


class CaseService:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.audit = AuditWriter(root / "audit.jsonl")
        self.active_case: Case | None = None

    def create_case(
        self,
        case_number: str,
        name: str,
        examiner: str,
        subject: str,
        description: str,
    ) -> Case:
        case = Case(str(uuid.uuid4()), case_number, name, examiner, utc_now(), subject, description)
        directory = self.root / case.case_id
        JsonRepository(directory / "case.json").write(case.__dict__)
        (directory / "evidence").mkdir()
        self.audit.append("local-user", "case.created", "case", case.case_id, {"case_number": case_number}, {"status": "success"})
        self.active_case = case
        return case

    def list_cases(self) -> list[Case]:
        cases = []
        for path in self.root.glob("*/case.json"):
            data = JsonRepository(path).read()
            cases.append(Case(**data))
        return sorted(cases, key=lambda case: case.created_at, reverse=True)

    def open_case(self, case_id: str) -> Case:
        data = JsonRepository(self.root / case_id / "case.json").read()
        self.active_case = Case(**data)
        self.active_case.status = "open"
        self._save(self.active_case)
        self.audit.append("local-user", "case.opened", "case", case_id, {}, {"status": "success"})
        return self.active_case

    def close_case(self) -> None:
        if self.active_case is None:
            return
        self.active_case.status = "closed"
        self._save(self.active_case)
        self.audit.append("local-user", "case.closed", "case", self.active_case.case_id, {}, {"status": "success"})
        self.active_case = None

    def update_case(self, case: Case) -> Case:
        self._save(case)
        if self.active_case and self.active_case.case_id == case.case_id:
            self.active_case = case
        self.audit.append("local-user", "case.updated", "case", case.case_id, {}, {"status": "success"})
        return case

    def _save(self, case: Case) -> None:
        JsonRepository(self.root / case.case_id / "case.json").write(case.__dict__)

    def case_path(self, case_id: str) -> Path:
        path = self.root / case_id
        if not path.is_dir():
            raise FileNotFoundError(str(path))
        return path

