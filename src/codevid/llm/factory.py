"""Factory for creating LLM providers."""

from codevid.llm.base import LLMError, LLMProvider
from codevid.models.project import LLMConfig, LLMProviderType


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    """Create an LLM provider from configuration.

    Args:
        config: LLM configuration specifying provider and settings.

    Returns:
        Configured LLM provider instance.

    Raises:
        LLMError: If the provider cannot be created.
    """
    if config.provider == LLMProviderType.ANTHROPIC:
        from codevid.llm.provider_anthropic import AnthropicProvider

        return AnthropicProvider(
            api_key=config.api_key,
            model=config.model,
        )

    elif config.provider == LLMProviderType.OPENAI:
        from codevid.llm.provider_openai import OpenAIProvider

        return OpenAIProvider(
            api_key=config.api_key,
            model=config.model,
            base_url=config.base_url,
        )

    elif config.provider == LLMProviderType.OLLAMA:
        from codevid.llm.provider_ollama import OllamaProvider

        return OllamaProvider(
            model=config.model,
            base_url=config.base_url,
        )

    elif config.provider == LLMProviderType.SIMPLE:
        from codevid.llm.provider_simple import SimpleLLM

        return SimpleLLM()

    else:
        raise LLMError(
            f"Unknown LLM provider: {config.provider}",
            provider=str(config.provider),
        )


def get_provider_for_name(
    provider_name: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider by name.

    This is a convenience function for creating providers without a full config.

    Args:
        provider_name: Name of the provider ("anthropic", "openai", "ollama").
        model: Optional model name override.
        api_key: Optional API key override.
        base_url: Optional base URL override.

    Returns:
        Configured LLM provider instance.
    """
    try:
        provider_type = LLMProviderType(provider_name.lower())
    except ValueError:
        raise LLMError(
            f"Unknown provider: {provider_name}. "
            f"Available: {', '.join(p.value for p in LLMProviderType)}",
            provider=provider_name,
        )

    config = LLMConfig(
        provider=provider_type,
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    return create_llm_provider(config)
