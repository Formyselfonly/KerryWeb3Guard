from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.blacklist import (
    BlacklistCase,
    BlacklistReportRequest,
    BlacklistReportResponse,
    BlacklistReviewRequest,
)

_CASES: dict[str, BlacklistCase] = {}


class BlacklistService:
    def submit_report(
        self,
        request: BlacklistReportRequest,
    ) -> BlacklistReportResponse:
        now = datetime.now(UTC)
        case = BlacklistCase(
            case_id=str(uuid4()),
            scammer_display_name=request.suspected_handle,
            platform=request.platform,
            contact_handle=request.suspected_handle,
            evidence_summary=request.description[:180],
            review_status="submitted",
            updated_at=now,
        )
        _CASES[case.case_id] = case
        return BlacklistReportResponse(
            message="Report received. Case is pending manual review.",
            case=case,
        )

    def list_cases(self) -> list[BlacklistCase]:
        return sorted(
            _CASES.values(),
            key=lambda item: item.updated_at,
            reverse=True,
        )

    def review_case(self, case_id: str, request: BlacklistReviewRequest) -> BlacklistCase:
        if case_id not in _CASES:
            raise KeyError(f"Case {case_id} not found.")

        old = _CASES[case_id]
        updated = old.model_copy(
            update={
                "review_status": request.review_status,
                "scammer_display_name": request.scammer_display_name
                or old.scammer_display_name,
                "evidence_summary": request.evidence_summary
                or old.evidence_summary,
                "updated_at": datetime.now(UTC),
            }
        )
        _CASES[case_id] = updated
        return updated
