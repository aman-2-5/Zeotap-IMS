from dataclasses import dataclass

from app.schemas import WorkItemStatus


@dataclass
class WorkItemContext:
    status: WorkItemStatus
    has_complete_rca: bool = False


class WorkItemState:
    allowed_transitions: set[WorkItemStatus] = set()

    def transition(self, context: WorkItemContext, target: WorkItemStatus) -> None:
        if target not in self.allowed_transitions:
            raise ValueError(f"Invalid transition from {context.status} to {target}")
        if target == WorkItemStatus.CLOSED and not context.has_complete_rca:
            raise ValueError("RCA is mandatory before closing incident")
        context.status = target


class OpenState(WorkItemState):
    allowed_transitions = {WorkItemStatus.INVESTIGATING}


class InvestigatingState(WorkItemState):
    allowed_transitions = {WorkItemStatus.RESOLVED}


class ResolvedState(WorkItemState):
    allowed_transitions = {WorkItemStatus.CLOSED, WorkItemStatus.INVESTIGATING}


class ClosedState(WorkItemState):
    allowed_transitions = set()


class WorkflowStateMachine:
    state_map = {
        WorkItemStatus.OPEN: OpenState(),
        WorkItemStatus.INVESTIGATING: InvestigatingState(),
        WorkItemStatus.RESOLVED: ResolvedState(),
        WorkItemStatus.CLOSED: ClosedState(),
    }

    @classmethod
    def transition(
        cls, current_status: WorkItemStatus, target_status: WorkItemStatus, has_complete_rca: bool
    ) -> WorkItemStatus:
        context = WorkItemContext(status=current_status, has_complete_rca=has_complete_rca)
        cls.state_map[current_status].transition(context, target_status)
        return context.status
