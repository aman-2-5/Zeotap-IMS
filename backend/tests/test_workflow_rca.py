import pytest

from app.schemas import WorkItemStatus
from app.workflow import WorkflowStateMachine


def test_close_without_rca_fails():
    with pytest.raises(ValueError):
        WorkflowStateMachine.transition(
            current_status=WorkItemStatus.RESOLVED,
            target_status=WorkItemStatus.CLOSED,
            has_complete_rca=False,
        )


def test_close_with_rca_succeeds():
    result = WorkflowStateMachine.transition(
        current_status=WorkItemStatus.RESOLVED,
        target_status=WorkItemStatus.CLOSED,
        has_complete_rca=True,
    )
    assert result == WorkItemStatus.CLOSED
