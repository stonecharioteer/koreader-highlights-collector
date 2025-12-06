from typing import Optional
import requests


def store_image_from_url(remote_url: str, rustfs_base: Optional[str]) -> Optional[str]:
    """Attempt to store remote_url into RustFS and return a local URL.

    Tries common patterns; falls back to returning None on failure so callers can keep original.
    """
    if not remote_url or not rustfs_base:
        return None

    base = rustfs_base.rstrip('/')
    session = requests.Session()
    # Allowed timeouts to avoid blocking UI
    timeout = 10

    # 1) Try a generic fetch endpoint: /fetch?url=
    try:
        r = session.post(f"{base}/fetch", params={"url": remote_url}, timeout=timeout)
        if r.ok:
            data = r.json() if r.headers.get('content-type', '').startswith('application/json') else None
            # Expect either {"url": "..."} or Location header
            if data and data.get('url'):
                return data['url']
            if r.headers.get('Location'):
                return r.headers['Location']
    except Exception:
        pass

    # 2) Try upload-by-url: /upload-url
    try:
        r = session.post(f"{base}/upload-url", json={"url": remote_url}, timeout=timeout)
        if r.ok:
            data = r.json() if r.headers.get('content-type', '').startswith('application/json') else None
            if data and data.get('url'):
                return data['url']
            if r.headers.get('Location'):
                return r.headers['Location']
    except Exception:
        pass

    # 3) Last resort: download then upload as multipart if service supports /upload
    try:
        get = session.get(remote_url, timeout=timeout)
        if get.ok:
            files = {"file": ("cover.jpg", get.content, get.headers.get('content-type') or 'image/jpeg')}
            up = session.post(f"{base}/upload", files=files, timeout=timeout)
            if up.ok:
                data = up.json() if up.headers.get('content-type', '').startswith('application/json') else None
                if data and data.get('url'):
                    return data['url']
                if up.headers.get('Location'):
                    return up.headers['Location']
    except Exception:
        pass

    return None


def store_image_from_bytes(content: bytes, content_type: Optional[str], rustfs_base: Optional[str], filename: str = "cover.jpg") -> Optional[str]:
    """Upload raw bytes to RustFS and return a local URL, or None on failure."""
    if not content or not rustfs_base:
        return None
    base = rustfs_base.rstrip('/')
    session = requests.Session()
    timeout = 10
    try:
        files = {"file": (filename, content, content_type or 'image/jpeg')}
        up = session.post(f"{base}/upload", files=files, timeout=timeout)
        if up.ok:
            data = up.json() if up.headers.get('content-type', '').startswith('application/json') else None
            if data and data.get('url'):
                return data['url']
            if up.headers.get('Location'):
                return up.headers['Location']
    except Exception:
        return None
    return None
