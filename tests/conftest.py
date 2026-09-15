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
"""

from __future__ import annotations

import pytest

from basinkit.exceptions import DataSourceError

# Refusals and outages: the source said no, or fell over. Not our defect.
_UPSTREAM_REFUSALS = (
    "access denied (403)",
    "not found (404)",
    "(429)",
    "(500)",
    "(502)",
    "(503)",
    "(504)",
    "timed out",
    "connection reset",
    "temporary failure in name resolution",
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
        if isinstance(current, DataSourceError):
            text = str(current).lower()
            if any(marker in text for marker in _UPSTREAM_REFUSALS):
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
