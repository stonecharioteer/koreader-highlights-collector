from typing import Optional, Tuple
import requests
import logging

logger = logging.getLogger(__name__)


def fetch_image_from_url(remote_url: str) -> Optional[Tuple[bytes, str]]:
    """Download image from remote URL and return (image_data, content_type).

    Returns tuple of (bytes, content_type) on success, None on failure.
    """
    if not remote_url:
        logger.warning("fetch_image_from_url: missing remote_url")
        return None

    try:
        logger.debug(f"Fetching image from {remote_url}")
        response = requests.get(remote_url, timeout=10)
        if response.ok:
            content_type = response.headers.get("content-type", "image/jpeg")
            logger.info(
                f"Successfully fetched image from {remote_url} ({len(response.content)} bytes, {content_type})"
            )
            return (response.content, content_type)
        else:
            logger.warning(
                f"Failed to fetch image from {remote_url}: HTTP {response.status_code}"
            )
            return None
    except Exception as e:
        logger.error(f"Error fetching image from {remote_url}: {e}")
        return None
