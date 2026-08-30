"""On-disk cache for downloaded tiles and derived basins.

basinkit downloads a lot of static data (DEM tiles, HydroBASINS, land cover)
that never changes. Caching it turns the second run of a script from minutes
into milliseconds, and makes the package usable offline once warm.

Cache location, in order of precedence:

1. ``BASINKIT_CACHE`` environment variable
2. the OS user cache directory (``platformdirs``)
3. ``~/.basinkit``
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path

import requests

from .exceptions import DataSourceError

_CHUNK = 1 << 20  # 1 MiB
_USER_AGENT = "basinkit/0.1.0 (+https://praddy-gbyte.github.io/basinkit)"


def cache_dir() -> Path:
    """Return the active cache directory, creating it if needed."""
    env = os.environ.get("BASINKIT_CACHE")
    if env:
        path = Path(env).expanduser()
    else:
        try:
            from platformdirs import user_cache_dir

            path = Path(user_cache_dir("basinkit", "basinkit"))
        except ImportError:
            path = Path.home() / ".basinkit"
    path.mkdir(parents=True, exist_ok=True)
    return path


def subdir(*parts: str) -> Path:
    path = cache_dir().joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _key(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def download(
    url: str,
    dest: Path | None = None,
    *,
    namespace: str = "downloads",
    force: bool = False,
    progress: bool = True,
    timeout: int = 60,
    headers: dict[str, str] | None = None,
    expected_min_bytes: int = 0,
) -> Path:
    """Download ``url`` into the cache and return the local path.

    A partially written file is never left at the final path: the download goes
    to a ``.part`` sibling and is renamed only on success, so an interrupted run
    cannot poison the cache with a truncated tile.
    """
    if dest is None:
        name = url.rstrip("/").split("/")[-1].split("?")[0] or "download"
        dest = subdir(namespace) / f"{_key(url)}_{name}"
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force and dest.stat().st_size > expected_min_bytes:
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    hdrs = {"User-Agent": _USER_AGENT, **(headers or {})}

    try:
        with requests.get(url, stream=True, timeout=timeout, headers=hdrs) as r:
            if r.status_code == 404:
                raise DataSourceError(f"Not found (404): {url}")
            if r.status_code in (401, 403):
                raise DataSourceError(
                    f"Access denied ({r.status_code}) for {url}\n"
                    "This route needs credentials. Check `basinkit catalog` for an "
                    "anonymous alternative."
                )
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            bar = None
            if progress and total > 4 << 20:
                try:
                    from tqdm import tqdm

                    bar = tqdm(
                        total=total, unit="B", unit_scale=True, unit_divisor=1024,
                        desc=dest.name[:40], leave=False,
                    )
                except ImportError:
                    pass

            with open(tmp, "wb") as fh:
                for chunk in r.iter_content(_CHUNK):
                    fh.write(chunk)
                    if bar is not None:
                        bar.update(len(chunk))
            if bar is not None:
                bar.close()
    except requests.RequestException as exc:
        tmp.unlink(missing_ok=True)
        raise DataSourceError(f"Download failed for {url}: {exc}") from exc

    tmp.replace(dest)
    return dest


def get_json(url: str, *, timeout: int = 60, params: dict | None = None) -> dict:
    """GET a JSON document with basinkit's user agent and error translation."""
    try:
        r = requests.get(
            url, timeout=timeout, params=params, headers={"User-Agent": _USER_AGENT}
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise DataSourceError(f"Request failed for {url}: {exc}") from exc


def memo_json(url: str, *, namespace: str = "json", max_age_days: float = 30) -> dict:
    """``get_json`` with an on-disk memo, for catalogue endpoints that rarely change."""
    path = subdir(namespace) / f"{_key(url)}.json"
    if path.exists():
        age_days = (time.time() - path.stat().st_mtime) / 86400
        if age_days < max_age_days:
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                path.unlink(missing_ok=True)
    data = get_json(url)
    path.write_text(json.dumps(data))
    return data


def info() -> dict:
    """Summarise what the cache currently holds."""
    root = cache_dir()
    total = 0
    counts: dict[str, int] = {}
    sizes: dict[str, int] = {}
    for p in root.rglob("*"):
        if p.is_file():
            size = p.stat().st_size
            total += size
            ns = p.relative_to(root).parts[0] if p.relative_to(root).parts else "."
            counts[ns] = counts.get(ns, 0) + 1
            sizes[ns] = sizes.get(ns, 0) + size
    return {
        "path": str(root),
        "total_bytes": total,
        "total_mb": round(total / 1e6, 1),
        "namespaces": {
            k: {"files": counts[k], "mb": round(sizes[k] / 1e6, 1)}
            for k in sorted(counts, key=lambda x: -sizes[x])
        },
    }


def clear(namespace: str | None = None) -> int:
    """Delete cached files. Returns bytes freed."""
    root = cache_dir() if namespace is None else cache_dir() / namespace
    if not root.exists():
        return 0
    freed = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    shutil.rmtree(root)
    cache_dir()
    return freed
