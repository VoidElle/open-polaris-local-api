from ..client import PolarisApiError


class PolarisAuthError(PolarisApiError):
    """Login rejected or session expired."""
