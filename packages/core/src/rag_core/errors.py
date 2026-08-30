"""Typed, safe error boundaries for domain and infrastructure failures."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_JOB_TRANSITION = "invalid_job_transition"
    MODEL_CONFIGURATION_ERROR = "model_configuration_error"
    MODEL_PROVIDER_ERROR = "model_provider_error"
    QUEUE_DISPATCH_ERROR = "queue_dispatch_error"


class RagError(Exception):
    code: ErrorCode
    retryable: bool
    public_message: str

    def __init__(
        self,
        code: ErrorCode,
        public_message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(public_message)
        self.code = code
        self.public_message = public_message
        self.retryable = retryable


class InvalidJobTransitionError(RagError):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            ErrorCode.INVALID_JOB_TRANSITION,
            f"Job status cannot transition from {current} to {target}",
        )


class ModelConfigurationError(RagError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.MODEL_CONFIGURATION_ERROR, message)


class ModelProviderError(RagError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(ErrorCode.MODEL_PROVIDER_ERROR, message, retryable=retryable)


class QueueDispatchError(RagError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.QUEUE_DISPATCH_ERROR, message, retryable=True)
