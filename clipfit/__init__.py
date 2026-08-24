"""clipfit - shrink oversized clipboard images so LLM chats can read them."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("clipfit")
except PackageNotFoundError:
    __version__ = "unknown"
