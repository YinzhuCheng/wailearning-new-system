from __future__ import annotations


class RetryableLLMError(Exception):
    pass


class NonRetryableLLMError(Exception):
    pass
