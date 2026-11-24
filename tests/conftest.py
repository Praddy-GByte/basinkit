"""Shared pytest configuration.

The one job here is telling two different kinds of red apart.

A ``network`` test exists to catch basinkit returning a *wrong answer* from a
live source. It does not exist to monitor whether the source is reachable from
whatever machine CI happens to run on. Those are different failures and only
one of them is ours: HydroSHEDS, for instance, answers 403 to GitHub Actions
runners because they are datacenter addresses, while the same request from a
laptop succeeds.

So an upstream refusal is reported as a skip, with the reason attached, and a
wrong number is still a failure. That keeps the weekly network run worth
reading -- red means basinkit is wrong, not that a server was moody.

The refusal is recognised by status code rather than by the wording of the
message. Matching text only ever worked for the two cases basinkit phrases
itself, 404 and 401/403: every other status reaches us through
``Response.raise_for_status``, whose message reads ``520 Server Error: ...``
with no parentheses, so fragments like ``"(500)"`` matched none of them. A 520
from HydroSHEDS turned the weekly run red for exactly that reason, and so
would have any 5xx or 429 since this file was written.
"""

from __future__ import annotations

import re

import pytest
import requests

from basinkit.exceptions import DataSourceError

#: Statuses that mean the source declined, not that basinkit is wrong.
#: 520-524 are Cloudflare's, reporting that the origin behind it misbehaved.
_REFUSAL_STATUS = frozenset(
    {401, 403, 404, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}
)

#: basinkit writes two of these messages itself and they carry no response
#: object, so the status is read back out of the text. The second pattern is
#: the shape ``raise_for_status`` produces.
_STATUS_IN_TEXT = (
    re.compile(r"\((\d{3})\)"),
    re.compile(r"\b(\d{3}) (?:Server|Client) Error\b"),
)

#: Transport failures, which never carry a status code at all.
_REFUSAL_TEXT = (
    "timed out",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remote end closed connection",
    "max retries exceeded",
    "temporary failure in name resolution",
    "name or service not known",
    "certificate verify failed",
)


def _upstream_refusal(exc: BaseException) -> BaseException | None:
    """The refusal in this exception's chain, if there is one.

    The refusal is not always the exception pytest ends up reporting. A test
    that wraps its call in ``pytest.warns`` gets ``Failed: DID NOT WARN``
    instead, with the original ``DataSourceError`` demoted to ``__context__``.
    Reading only the outermost exception turned the weekly source check red
    three runs running, for a 403 that HydroSHEDS serves to every datacenter
    address and to no laptop.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))

        status = getattr(getattr(current, "response", None), "status_code", None)
        if status in _REFUSAL_STATUS:
            return current

        # SSLError and the DNS failures are ConnectionError subclasses, so the
        # isinstance covers them without naming each one.
        if isinstance(current, requests.ConnectionError):
            return current

        if isinstance(current, (DataSourceError, OSError, requests.RequestException)):
            text = str(current)
            for pattern in _STATUS_IN_TEXT:
                found = pattern.search(text)
                if found and int(found.group(1)) in _REFUSAL_STATUS:
                    return current
            lowered = text.lower()
            if any(marker in lowered for marker in _REFUSAL_TEXT):
                return current

        current = current.__cause__ or current.__context__
    return None


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return
    if "network" not in item.keywords:
        return
    if call.excinfo is None:
        return
    refusal = _upstream_refusal(call.excinfo.value)
    if refusal is None:
        return

    # pytest renders a skip from a (path, lineno, reason) triple; a bare string
    # trips an assertion in its own summary writer.
    relpath, lineno, _ = item.location
    report.outcome = "skipped"
    report.longrepr = (
        relpath,
        (lineno or 0) + 1,
        f"upstream unavailable, not a basinkit failure: {refusal}",
    )
