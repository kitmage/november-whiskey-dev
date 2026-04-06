class ConfigError(RuntimeError):
    """Configuration error."""


class HubSpotAPIError(RuntimeError):
    """HubSpot API request failure."""


class GraphAPIError(RuntimeError):
    """Microsoft Graph request failure."""


class AvailabilityError(RuntimeError):
    """No valid availability or malformed availability payload."""


class WorkflowError(RuntimeError):
    """Workflow-level orchestration failure."""
