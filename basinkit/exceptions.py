"""Exceptions carrying enough context to act on."""

from __future__ import annotations


class BasinkitError(Exception):
    """Base for every basinkit error."""


class DelineationError(BasinkitError):
    """The upstream basin could not be resolved from the given outlet."""


class OutletSnapError(DelineationError):
    """The outlet point could not be snapped to a river reach.

    Almost always means the coordinate is not on a mapped channel. The fix is
    usually to raise ``snap_tolerance`` or move the point onto the blue line.
    """


class DataSourceError(BasinkitError):
    """A remote data source failed."""


class LicenseError(BasinkitError):
    """A dataset was requested whose licence forbids the intended use."""


class NotImplementedSource(BasinkitError):
    """A catalogued dataset that basinkit cannot fetch.

    Raised instead of letting the catalogue imply a capability the code does
    not have. The message carries the access route, the licence and what to do
    with the data once you have it.
    """


class MissingDependency(BasinkitError):
    """An optional dependency is needed for this path."""

    def __init__(self, package: str, extra: str) -> None:
        super().__init__(
            f"This needs the optional dependency {package!r}.\n"
            f"    pip install 'basinkit[{extra}]'"
        )
        self.package = package
        self.extra = extra
