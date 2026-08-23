"""papeete-actor-synchronous-messaging-http — an HTTP binding for papeete-actor-synchronous-messaging.

ONE CLASS, AND IT IS A `Mailbox`. `papeete-actor-synchronous-messaging`'s own `mailbox.py`
already names the port this fills: *"A queue, an HTTP surface, a file drop or a GitHub issue is
a NEW BINDING, not a variant of this one."* This package is that binding for HTTP, and nothing
else — no card rule, no membrane rule, no engine, re-authored or restated here.
"""
from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("papeete-actor-synchronous-messaging-http")
except PackageNotFoundError:      # a source tree that was never installed
    __version__ = "0.0.0+source"

__all__ = ["__version__"]
