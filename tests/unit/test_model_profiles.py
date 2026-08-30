from pydantic import SecretStr
from rag_core.config import AppSettings
from rag_core.models.profiles import ModelPurpose


def test_default_groq_profiles_are_capability_specific() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]  # Pydantic Settings runtime option.
        groq_api_key=SecretStr("test-key"),
    )

    profiles = settings.model_profiles()

    assert set(profiles) == {purpose.value for purpose in ModelPurpose}
    assert profiles[ModelPurpose.FAST_STRUCTURED].supports_strict_structured_output
    assert profiles[ModelPurpose.AGENT].supports_tool_calling
    assert profiles[ModelPurpose.QUALITY].provider == "groq"


def test_groq_key_is_redacted_in_settings_output() -> None:
    settings = AppSettings(
        _env_file=None,  # type: ignore[call-arg]  # Pydantic Settings runtime option.
        groq_api_key=SecretStr("super-secret"),
    )

    assert "super-secret" not in str(settings)
