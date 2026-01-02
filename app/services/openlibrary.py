from typing import Optional, Dict, List
import re
import requests


OL_BASE = "https://openlibrary.org"
COVERS = "https://covers.openlibrary.org/b/id/{id}-L.jpg"


def _ua(app_name: Optional[str], email: Optional[str]) -> str:
    name = (app_name or "KoReaderHighlightsApp")[:50]
    contact = (email or "user@example.com")[:100]
    return f"{name} (contact: {contact})"


def _session(app_name: Optional[str], email: Optional[str]) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _ua(app_name, email)})
    return s


def extract_key(url: str) -> Optional[str]:
    # Matches /works/OL...W or /books/OL...M
    m = re.search(r"/(works|books)/(OL[0-9]+[WM])", url)
    if m:
        return f"/{m.group(1)}/{m.group(2)}"
    return None


def fetch_from_search(
    query: str, app_name: Optional[str], email: Optional[str]
) -> Dict[str, Optional[str]]:
    sess = _session(app_name, email)
    resp = sess.get(f"{OL_BASE}/search.json", params={"q": query}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    docs: List[dict] = data.get("docs") or []
    if not docs:
        return {"title": None, "authors": None, "image": None, "url": None}
    d0 = docs[0]
    title = d0.get("title")
    authors = ", ".join(d0.get("author_name") or []) or None
    cover_id = d0.get("cover_i")
    image = COVERS.format(id=cover_id) if cover_id else None
    key = d0.get("key")  # e.g., "/works/OL...W"
    url = f"{OL_BASE}{key}" if key else None
    return {"title": title, "authors": authors, "image": image, "url": url}


def search(
    query: str, app_name: Optional[str], email: Optional[str], limit: int = 5
) -> List[Dict[str, Optional[str]]]:
    sess = _session(app_name, email)
    resp = sess.get(
        f"{OL_BASE}/search.json", params={"q": query, "limit": limit}, timeout=10
    )
    resp.raise_for_status()
    data = resp.json()
    docs: List[dict] = data.get("docs") or []
    results: List[Dict[str, Optional[str]]] = []
    for d in docs[:limit]:
        title = d.get("title")
        authors = ", ".join(d.get("author_name") or []) or None
        cover_id = d.get("cover_i")
        image = COVERS.format(id=cover_id) if cover_id else None
        key = d.get("key")  # "/works/OL...W"
        url = f"{OL_BASE}{key}" if key else None
        results.append(
            {"title": title, "authors": authors, "image": image, "url": url, "key": key}
        )
    return results


def fetch_from_url(
    url: str, app_name: Optional[str], email: Optional[str]
) -> Dict[str, Optional[str]]:
    sess = _session(app_name, email)
    key = extract_key(url)
    if not key:
        # treat as a search string
        return fetch_from_search(url, app_name, email)
    resp = sess.get(f"{OL_BASE}{key}.json", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    title = data.get("title")
    image = None
    covers = data.get("covers") or []
    if covers:
        image = COVERS.format(id=covers[0])
    # Authors
    authors = None
    author_entries = data.get("authors") or []
    names: List[str] = []
    for ae in author_entries[:3]:  # cap to 3 lookups
        akey = (ae.get("author") or {}).get("key")
        if not akey:
            continue
        try:
            ar = sess.get(f"{OL_BASE}{akey}.json", timeout=10)
            if ar.ok:
                aname = (ar.json() or {}).get("name")
                if aname:
                    names.append(aname)
        except Exception:
            continue
    if names:
        authors = ", ".join(names)
    return {
        "title": title,
        "authors": authors,
        "image": image,
        "url": f"{OL_BASE}{key}",
    }
