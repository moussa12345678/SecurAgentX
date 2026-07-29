"""URL validation utilities to prevent SSRF attacks."""
from urllib.parse import urlparse

ALLOWED_SCHEMES = {"http", "https"}


def validate_url_scheme(url: str) -> str:
    """Validate that URL uses http or https scheme only.

    Returns the URL if valid, raises ValueError otherwise.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(
            f"URL scheme '{parsed.scheme}' not allowed. Only http/https are permitted."
        )
    return url
