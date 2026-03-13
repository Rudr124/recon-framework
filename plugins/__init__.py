"""Plugins package.

Drop files named *_plugin.py into this directory and they will be
auto-discovered by `core.plugin_manager` when the main runner executes.
Each plugin should expose a `run(target: str)` function which will be
called with the target domain (or subdomain) string.
"""

__all__ = []
