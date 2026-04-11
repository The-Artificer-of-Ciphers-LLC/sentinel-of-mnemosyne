"""Shared retry configuration for all HTTP clients (DUP-03 / PROV-03)."""

from tenacity import stop_after_attempt, wait_exponential

RETRY_ATTEMPTS = 3
RETRY_STOP = stop_after_attempt(RETRY_ATTEMPTS)
RETRY_WAIT = wait_exponential(multiplier=1, min=1, max=4)
HARD_TIMEOUT_SECONDS = 30
