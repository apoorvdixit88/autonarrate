# Auto-narrated video tool

from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("autonarrate")
except PackageNotFoundError:
    __version__ = "unknown"
