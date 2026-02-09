"""Claude API client wrapper."""

from typing import Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from polaris.config import Settings, get_settings


class ClaudeClientError(Exception):
    """Error from Claude API."""

    pass


class ClaudeClient:
    """Wrapper for Anthropic Claude API."""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 1024

    def __init__(
        self,
        api_key: Optional[str] = None,
        settings: Optional[Settings] = None,
    ):
        self.settings = settings or get_settings()
        self.api_key = api_key or self.settings.anthropic_api_key

        if not self.api_key:
            raise ClaudeClientError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY environment variable."
            )

        self.client = anthropic.Anthropic(api_key=self.api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = MAX_TOKENS,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        """Generate text using Claude.

        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt for context
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
            model: Model to use (defaults to claude-sonnet-4-20250514)

        Returns:
            Generated text response
        """
        model = model or self.DEFAULT_MODEL

        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Extract text from response
            if message.content and len(message.content) > 0:
                return message.content[0].text
            return ""

        except anthropic.APIError as e:
            raise ClaudeClientError(f"API error: {e}") from e
        except anthropic.AuthenticationError as e:
            raise ClaudeClientError(f"Authentication error: {e}") from e

    def generate_with_context(
        self,
        messages: list[dict[str, str]],
        system_prompt: Optional[str] = None,
        max_tokens: int = MAX_TOKENS,
        temperature: float = 0.7,
        model: Optional[str] = None,
    ) -> str:
        """Generate text with multi-turn context.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            model: Model to use

        Returns:
            Generated text response
        """
        model = model or self.DEFAULT_MODEL

        try:
            message = self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt or "",
                messages=messages,
            )

            if message.content and len(message.content) > 0:
                return message.content[0].text
            return ""

        except anthropic.APIError as e:
            raise ClaudeClientError(f"API error: {e}") from e

    def count_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Note: This is an approximation. For exact counts, use the API.
        """
        # Rough approximation: ~4 characters per token for English
        return len(text) // 4
