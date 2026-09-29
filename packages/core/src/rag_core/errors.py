"""Typed, safe error boundaries for domain and infrastructure failures."""

from enum import StrEnum


class ErrorCode(StrEnum):
    INVALID_JOB_TRANSITION = "invalid_job_transition"
    MODEL_CONFIGURATION_ERROR = "model_configuration_error"
    MODEL_PROVIDER_ERROR = "model_provider_error"
    QUEUE_DISPATCH_ERROR = "queue_dispatch_error"
    RETRIEVAL_EXECUTION_ERROR = "retrieval_execution_error"
    INGESTION_STORAGE_ERROR = "ingestion_storage_error"
    DOCUMENT_PARSING_ERROR = "document_parsing_error"
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"


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


class RetrievalExecutionError(RagError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(ErrorCode.RETRIEVAL_EXECUTION_ERROR, message, retryable=retryable)


class IngestionStorageError(RagError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(ErrorCode.INGESTION_STORAGE_ERROR, message, retryable=retryable)


class DocumentParsingError(RagError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.DOCUMENT_PARSING_ERROR, message, retryable=False)


class AuthenticationError(RagError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.AUTHENTICATION_ERROR, message, retryable=False)


class AuthorizationError(RagError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.AUTHORIZATION_ERROR, message, retryable=False)
