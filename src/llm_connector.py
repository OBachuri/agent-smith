from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI
from threading import Lock


class LLMError(RuntimeError):
    """All configured API keys failed."""


class LLMConnector:
    """
    Connector with providers with a list of keys.
    """

    def __init__(self, config: ProviderConfig) -> None:

        if not config.api_keys:
            raise ValueError(
                f"No API keys configured for {config.name}"
            )

        self.config = config
        self._clients = [
            OpenAI(
                api_key=key,
                base_url=config.base_url,
                max_retries=0,
                timeout=60.0,
            )
            for key in config.api_keys
        ]

        self._index = 0
        self._lock = Lock()

    @staticmethod
    def _should_retry(exc: Exception) -> bool:
        if isinstance(exc, (APIConnectionError, APITimeoutError)):
            return True

        if isinstance(exc, APIStatusError):
            return exc.status_code in {
                401, 403, 408, 429, 500, 502, 503, 504
            }

        return False


# class LLMConnector:
#     def __init__(self, api_keys_config: dict[str, list[str]]):
#         """
#         Initialize the connector with a dictionary mapping providers
#         to a list of keys.
#         Example:
#             api_keys_config = {
#                 "groq": ["gsk_key1...", "gsk_key2..."],
#                 "gemini": ["AIzaSyKey1...", "AIzaSyKey2..."],
#                 "openrouter": ["sk-or-v1..."]
#             }
#         """
#         self.api_keys = api_keys_config
