"""
Plugin manager for user-supplied plugin scripts.

Drop files named *_plugin.py into the top-level `plugins/` directory.
Each plugin must expose a `run(target: str)` function. Plugins may do
their own logging, saving, or posting to Discord; the manager will simply
discover, load, enable/disable according to `plugins/plugins.json`, and
invoke the `run()` function.
"""
import os
import json
import importlib
from typing import Dict, Any

from . import config, utils
import core.reporting as reporting


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
PLUGINS_DIR = os.path.join(PROJECT_ROOT, "plugins")
PLUGINS_CONFIG = os.path.join(PLUGINS_DIR, "plugins.json")


def _load_config() -> Dict[str, Any]:
    if not os.path.exists(PLUGINS_CONFIG):
        return {}
    try:
        with open(PLUGINS_CONFIG, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        utils.log("[PLUGINS] Failed to read plugins/plugins.json; falling back to all-enabled", "warn")
        return {}


def _save_config(cfg: Dict[str, Any]):
    try:
        os.makedirs(PLUGINS_DIR, exist_ok=True)
        with open(PLUGINS_CONFIG, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
    except Exception as e:
        utils.log(f"[PLUGINS] Failed to save plugin config: {e}", "warn")


def discover_plugins() -> Dict[str, str]:

    plugins = {}
    if not os.path.isdir(PLUGINS_DIR):
        return plugins

    for fname in os.listdir(PLUGINS_DIR):
        if fname.endswith("_plugin.py") and fname != "__init__.py":
            name = fname[:-3]
            module_path = f"plugins.{name}"
            plugins[name] = module_path
    return plugins


def load_plugins() -> Dict[str, Any]:

    loaded = {}
    plugins = discover_plugins()
    for name, module_path in plugins.items():
        try:
            mod = importlib.import_module(module_path)
            loaded[name] = mod
            utils.log(f"[PLUGINS] Loaded plugin: {name}")
        except Exception as e:
            utils.log(f"[PLUGINS] Failed to import {name}: {e}", "warn")
    return loaded


def run_plugins(target: str, only_enabled: bool = True) -> Dict[str, Any]:

    results = {}
    cfg = _load_config()
    mods = load_plugins()
    for name, mod in mods.items():
        enabled = True
        try:
            enabled = bool(cfg.get(name, {}).get("enabled", True))
        except Exception:
            enabled = True

        if only_enabled and not enabled:
            utils.log(f"[PLUGINS] Skipping disabled plugin: {name}")
            continue

        if not hasattr(mod, "run"):
            utils.log(f"[PLUGINS] Plugin {name} missing run(target) — skipping", "warn")
            continue

        try:
            utils.log(f"[PLUGINS] Executing plugin: {name} ...")
            out = mod.run(target)
            results[name] = {"ok": True, "result": out}
            utils.log(f"[PLUGINS] Plugin {name} completed.")
            # If plugin returned saved file paths, attach to report
            try:
                if isinstance(out, dict):
                    for k, v in out.items():
                        if isinstance(v, str) and v:
                            try:
                                if os.path.exists(v):
                                    reporting.attach_file_section(f"Plugin:{name}:{k}", v)
                            except Exception:
                                continue
                        # if plugin returned a directory
                        if isinstance(v, str) and os.path.isdir(v):
                            try:
                                reporting.append_section(f"Plugin:{name}:{k}", f"Directory: {v}")
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception as e:
            results[name] = {"ok": False, "error": str(e)}
            utils.log(f"[PLUGINS] Plugin {name} failed: {e}", "warn")

    return results


def list_plugins() -> Dict[str, Any]:
    """Return available plugins and their enabled state from config."""
    cfg = _load_config()
    discovered = discover_plugins()
    out = {}
    for name in discovered.keys():
        out[name] = {"enabled": bool(cfg.get(name, {}).get("enabled", True))}
    return out


def set_plugin_enabled(name: str, enabled: bool):
    cfg = _load_config()
    cur = cfg.get(name, {})
    cur["enabled"] = bool(enabled)
    cfg[name] = cur
    _save_config(cfg)
