from uuid import uuid4

import pytest
from pydantic import ValidationError
from rag_core.retrieval.models import AnswerStatus, Citation, GroundedAnswer


def test_grounded_answer_requires_a_citation() -> None:
    with pytest.raises(ValidationError, match="at least one citation"):
        GroundedAnswer(
            status=AnswerStatus.ANSWERED,
            text="An unsupported answer",
            confidence=0.8,
        )


def test_grounded_answer_accepts_evidence_reference() -> None:
    document_id = uuid4()
    answer = GroundedAnswer(
        status=AnswerStatus.ANSWERED,
        text="The policy was updated.",
        confidence=0.9,
        citations=(
            Citation(
                ordinal=1,
                chunk_id=uuid4(),
                document_id=document_id,
                source_label="Policy handbook",
            ),
        ),
    )

    assert answer.citations[0].document_id == document_id
