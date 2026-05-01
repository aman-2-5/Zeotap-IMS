from app.schemas import Severity


class AlertStrategy:
    async def alert(self, component_id: str, message: str) -> str:
        raise NotImplementedError


class PagerDutyAlert(AlertStrategy):
    async def alert(self, component_id: str, message: str) -> str:
        return f"[PagerDuty] {component_id}: {message}"


class SlackAlert(AlertStrategy):
    async def alert(self, component_id: str, message: str) -> str:
        return f"[Slack] {component_id}: {message}"


class EmailAlert(AlertStrategy):
    async def alert(self, component_id: str, message: str) -> str:
        return f"[Email] {component_id}: {message}"


class AlertStrategyFactory:
    @staticmethod
    def for_severity(severity: Severity) -> AlertStrategy:
        if severity == Severity.P0:
            return PagerDutyAlert()
        if severity == Severity.P1:
            return SlackAlert()
        return EmailAlert()
