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
_UA_TEMPLATE = "basinkit/{} (+https://praddy-gbyte.github.io/basinkit)"


def _user_agent() -> str:
    """The User-Agent every request carries, built from the package version.

    The version is read when a request is made, not when this module is
    imported: ``basinkit/__init__.py`` imports this module on its way to
    defining ``__version__``, so the name does not exist yet at import time.
    Hard-coding it here is what left every provider seeing 0.1.0 long after
    0.1.0 had shipped.
    """
    from . import __version__

    return _UA_TEMPLATE.format(__version__)


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



#: Whether to hash what arrives. A digest is what turns "this run used
#: WorldCover 2021" from something to believe into something a later run can
#: check, so it is on by default; set it False to skip the cost where
#: reproducibility is not the point.
HASH_DOWNLOADS = True

#: Every cached file this process has read or fetched, oldest first. Append
#: only: a run that read the same tile twice read it twice.
_LEDGER: list[dict] = []


def _sha256(path: Path) -> str | None:
    """The file's digest, computed once and kept in a sidecar beside it.

    A 530 MB reach table costs seconds to hash, which is worth paying once and
    not on every run, so the digest is written next to the file and read back
    while the sidecar is no older than the file it describes. The sidecar is
    advisory: anything that does not look like a digest is recomputed, and a
    cache that cannot be written to is still usable.
    """
    if not HASH_DOWNLOADS:
        return None
    try:
        side = path.with_suffix(path.suffix + ".sha256")
        if side.exists() and side.stat().st_mtime >= path.stat().st_mtime:
            kept = side.read_text(encoding="utf-8").strip()
            if len(kept) == 64:
                return kept
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        out = digest.hexdigest()
        try:
            side.write_text(out, encoding="utf-8")
        except OSError:
            pass
        return out
    except OSError:
        return None


def _record(url: str, path: Path, *, from_cache: bool) -> None:
    """Note that this file was used, and what was in it."""
    try:
        size = path.stat().st_size
    except OSError:
        size = None
    _LEDGER.append({"url": url, "path": str(path), "bytes": size,
                    "sha256": _sha256(path), "from_cache": from_cache})


def ledger() -> list[dict]:
    """Every cached file read or fetched so far, oldest first."""
    return list(_LEDGER)


def clear_ledger() -> None:
    """Forget what has been read. The cached files themselves are untouched."""
    _LEDGER.clear()


def recheck(sources: list[dict]) -> list[dict]:
    """Compare a run's recorded sources against what is in the cache now.

    This is the point of recording a digest rather than a date. A date says
    when a file was read; a digest says what was in it, so a study repeated six
    months later can be told whether its own change moved the answer or the
    provider reissued a tile underneath it.

    Each entry comes back with ``status``:

    ``unchanged``   the bytes in the cache still hash to what was recorded
    ``changed``     the file is there and hashes to something else
    ``absent``      the file is no longer in the cache
    ``unverifiable``  nothing was recorded to compare against
    """
    out = []
    for source in sources or []:
        was = source.get("sha256")
        entry = {"url": source.get("url"), "recorded_sha256": was}
        path = _find_cached(source.get("url"))
        if was is None:
            entry["status"] = "unverifiable"
        elif path is None:
            entry["status"] = "absent"
        else:
            now = _sha256(path)
            entry["current_sha256"] = now
            entry["status"] = "unchanged" if now == was else "changed"
        out.append(entry)
    return out


def _find_cached(url: str | None) -> Path | None:
    """The cached file for ``url``, wherever in the cache it was put.

    A record carries no local path on purpose: a path names one machine, and
    these records are meant to travel with a study. The cache file name begins
    with a digest of the URL, so the URL is enough to find it again on any
    machine that has it.
    """
    if not url:
        return None
    key = _key(url)
    try:
        for found in cache_dir().rglob(f"{key}_*"):
            if found.is_file() and found.suffix != ".sha256":
                return found
    except OSError:
        pass
    return None


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
        _record(url, dest, from_cache=True)
        return dest

    tmp = dest.with_suffix(dest.suffix + ".part")
    hdrs = {"User-Agent": _user_agent(), **(headers or {})}

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
    _record(url, dest, from_cache=False)
    return dest


def get_json(url: str, *, timeout: int = 60, params: dict | None = None) -> dict:
    """GET a JSON document with basinkit's user agent and error translation."""
    try:
        r = requests.get(
            url, timeout=timeout, params=params, headers={"User-Agent": _user_agent()}
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
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                path.unlink(missing_ok=True)
    data = get_json(url)
    path.write_text(json.dumps(data), encoding="utf-8")
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
