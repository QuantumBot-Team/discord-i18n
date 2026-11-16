"""
Core translation engine for discord-i18n.

Attribution
-----------
The following concepts and patterns are inspired by / adapted from
**ezcord** (https://github.com/tibue99/ezcord), which is licensed under
the MIT License (Copyright © tibue99):

* ``load_languages()`` — directory-based YAML/JSON locale loading
* ``en`` key auto-expansion to ``en-US`` + ``en-GB``
* ``general`` section variable expansion (``{.key}`` syntax)
* Locale fallback chain logic
* Missing-key modes (``"key"`` / ``"empty"`` / ``"raise"``)

Original source: https://github.com/tibue99/ezcord/blob/main/ezcord/i18n.py
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

from .locale import Locale

log = logging.getLogger(__name__)

# Matches {variable} placeholders, but NOT {{ escaped braces }}
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")


class TranslationNotFoundError(KeyError):
    """Raised when a translation key is missing and no fallback is available."""


class I18n:
    """
    Central i18n registry.

    Parameters
    ----------
    default_locale:
        Locale string used when no other locale is resolved (default ``en-US``).
    localizations:
        Pre-built dict in **ezcord style**: ``{"en-US": {...}, "de": {...}}``.
        When given, :meth:`load` does not need to be called.
        Use :func:`load_languages` to build this dict from a folder of YAML/JSON
        files, exactly like ezcord does.
    locales_dir:
        Directory that contains one JSON **or** YAML file per locale
        (e.g. ``locales/de.yaml``, ``locales/en-US.json``).
        Only used when *localizations* is ``None``.
    fallback_locale:
        Secondary locale tried when a key is missing in the requested locale.
        Defaults to *default_locale*.
    missing_key_mode:
        How to handle missing translation keys:

        * ``"raise"``  – raise :class:`TranslationNotFoundError`
        * ``"key"``    – return the raw key string *(default)*
        * ``"empty"``  – return an empty string
    """

    def __init__(
        self,
        default_locale: str = "en-US",
        localizations: dict[str, dict[str, Any]] | None = None,
        locales_dir: str | os.PathLike[str] = "locales",
        fallback_locale: str | None = None,
        missing_key_mode: str = "key",
    ) -> None:
        self._default_locale = Locale.from_str(default_locale)
        self._fallback_locale = Locale.from_str(fallback_locale or default_locale)
        self._locales_dir = Path(locales_dir)
        self._missing_key_mode = missing_key_mode
        # ezcord-style: pre-populated via load_languages()
        self._data: dict[str, dict[str, Any]] = dict(localizations) if localizations else {}
        # Expand bare "en" key to both en-GB and en-US, like ezcord
        if "en" in self._data:
            en_data = self._data.pop("en")
            self._data.setdefault("en-US", {})
            self._data.setdefault("en-GB", {})
            _deep_merge(self._data["en-US"], en_data)
            _deep_merge(self._data["en-GB"], en_data)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Load all ``*.json``, ``*.yaml``, and ``*.yml`` locale files from
        *locales_dir*.

        Call this once during bot startup, e.g. inside ``on_ready``.
        When you pass *localizations* to the constructor (ezcord style via
        :func:`load_languages`), calling ``load()`` is not required.
        """
        if not self._locales_dir.exists():
            raise FileNotFoundError(
                f"Locales directory not found: {self._locales_dir!r}"
            )

        loaded: list[str] = []
        patterns = ["**/*.json", "**/*.yaml", "**/*.yml"]
        seen: set[Path] = set()
        for pattern in patterns:
            for path in self._locales_dir.glob(pattern):
                if path in seen:
                    continue
                seen.add(path)

                # Support flat layout:  locales/de.yaml  → "de"
                # Support nested layout: locales/de/commands.yaml → "de"
                locale_key = path.stem if path.parent == self._locales_dir else path.parent.name

                data = _parse_file(path)
                if data is None:
                    continue

                # Merge nested files for the same locale
                if locale_key in self._data:
                    _deep_merge(self._data[locale_key], data)
                else:
                    self._data[locale_key] = data

                loaded.append(locale_key)

        # Expand bare "en" key → en-US + en-GB (ezcord convention)
        if "en" in self._data:
            en_data = self._data.pop("en")
            self._data.setdefault("en-US", {})
            self._data.setdefault("en-GB", {})
            _deep_merge(self._data["en-US"], en_data)
            _deep_merge(self._data["en-GB"], en_data)

        log.info("discord-i18n loaded locales: %s", sorted(set(loaded)))

    def reload(self) -> None:
        """Clear the cache and reload all locale files."""
        self._data.clear()
        self.load()

    def add_locale(self, locale: str, data: dict[str, Any]) -> None:
        """
        Register translations programmatically (without a file).

        Parameters
        ----------
        locale:
            Locale string, e.g. ``"de"`` or ``"en-US"``.
        data:
            Flat or nested dict of translation keys → strings.
        """
        if locale in self._data:
            _deep_merge(self._data[locale], data)
        else:
            self._data[locale] = data

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def t(
        self,
        key: str,
        locale: str | Locale | None = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Translate *key* into *locale*.

        Parameters
        ----------
        key:
            Dot-separated key path, e.g. ``"commands.ping.response"``.
        locale:
            Target locale string or :class:`Locale` object.
            Falls back to *default_locale* when ``None``.
        count:
            When provided, enables plural selection.
            The translation value may be a dict with keys ``"one"`` and
            ``"other"`` (and optionally ``"zero"``).
        **kwargs:
            Named placeholders to interpolate into the translated string.

        Returns
        -------
        str
            The translated and interpolated string.
        """
        resolved = Locale.from_str(str(locale)) if locale else self._default_locale

        raw = self._lookup(key, resolved, count)
        if raw is None:
            return self._handle_missing(key)

        return _interpolate(raw, **kwargs)

    def get_translator(self, locale: str | Locale) -> "Translator":
        """
        Return a :class:`Translator` bound to *locale*.

        Useful inside cogs / command handlers::

            t = i18n.get_translator(interaction.locale)
            await interaction.response.send_message(t("ping.pong"))
        """
        return Translator(i18n=self, locale=str(locale))

    # ------------------------------------------------------------------
    # Available locales
    # ------------------------------------------------------------------

    @property
    def available_locales(self) -> list[str]:
        """Return a list of all loaded locale strings."""
        return list(self._data.keys())

    # ------------------------------------------------------------------
    # Number formatting
    # ------------------------------------------------------------------

    def format_number(
        self,
        value: int | float,
        locale: str | Locale | None = None,
        *,
        decimal_places: int | None = None,
    ) -> str:
        """
        Format *value* using locale-aware thousands and decimal separators.

        Locales that use a period as thousands separator (e.g. ``de``, ``tr``,
        ``pt-BR``) and a comma as decimal separator are handled automatically.
        All others use the common ``1,234.56`` format.

        Parameters
        ----------
        value:
            The number to format.
        locale:
            Target locale. Falls back to *default_locale* when ``None``.
        decimal_places:
            If given, the number is rounded to this many decimal places.
            When ``None``, floats keep their natural representation and
            integers are formatted without a decimal part.

        Examples
        --------
        >>> i18n.format_number(1234567, locale="de")
        '1.234.567'
        >>> i18n.format_number(1234567.89, locale="en-US", decimal_places=2)
        '1,234,567.89'
        """
        loc = Locale.from_str(str(locale)) if locale else self._default_locale
        lang = loc.language

        # Locales that swap separators (thousands='.', decimal=',')
        period_thousands = {"de", "tr", "pt", "it", "nl", "pl", "cs", "hu", "ro",
                            "da", "hr", "lt", "no", "sv", "fi", "el", "bg", "uk"}

        if decimal_places is not None:
            formatted = f"{value:,.{decimal_places}f}"
        elif isinstance(value, int):
            formatted = f"{value:,}"
        else:
            # float: strip insignificant trailing zeros after decimal point
            # (e.g. 1234.0 -> "1,234", 1.50 -> "1.5") to match the docstring
            formatted = f"{value:,}"
            if "." in formatted:
                formatted = formatted.rstrip("0").rstrip(".")

        if lang in period_thousands:
            # swap: ',' ↔ '.'
            formatted = formatted.replace(",", "\x00").replace(".", ",").replace("\x00", ".")

        return formatted

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_json(
        self,
        path: str | os.PathLike[str],
        *,
        indent: int = 2,
        locale: str | None = None,
    ) -> None:
        """
        Write the loaded translations to a JSON file.

        Useful for sharing translations with a web frontend or for debugging.

        Parameters
        ----------
        path:
            Destination file path (e.g. ``"dist/i18n.json"``).
        indent:
            JSON indentation level. Defaults to ``2``.
        locale:
            When given, export only that locale's data.
            When ``None`` (default), export all locales.

        Examples
        --------
        ::

            i18n.export_json("dist/i18n.json")
            # or: i18n.export_json("dist/de.json", locale="de")
        """
        data = self._data.get(locale, {}) if locale else self._data
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        log.info("discord-i18n: exported translations to %s", out)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lookup(
        self,
        key: str,
        locale: Locale,
        count: int | None,
    ) -> str | None:
        """
        Try to find *key* by walking the fallback chain.
        Returns ``None`` when the key is absent in every candidate locale.
        """
        candidates = locale.fallback_chain()
        # Also try the configured fallback locale
        for fb in self._fallback_locale.fallback_chain():
            if fb not in candidates:
                candidates.append(fb)

        for candidate in candidates:
            data = self._data.get(candidate)
            if data is None:
                continue
            value = _get_nested(data, key)
            if value is None:
                continue
            return _select_plural(value, count)

        return None

    def _handle_missing(self, key: str) -> str:
        if self._missing_key_mode == "raise":
            raise TranslationNotFoundError(key)
        if self._missing_key_mode == "empty":
            return ""
        # default: return the key itself
        log.debug("Missing translation key: %r", key)
        return key


class Translator:
    """
    A callable bound to a specific locale.

    Returned by :meth:`I18n.get_translator`.  Call it like a function::

        t = i18n.get_translator("de")
        msg = t("errors.not_found", item="Server")
    """

    def __init__(self, i18n: I18n, locale: str) -> None:
        self._i18n = i18n
        self._locale = locale

    @property
    def locale(self) -> str:
        return self._locale

    def __call__(
        self,
        key: str,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        return self._i18n.t(key, locale=self._locale, count=count, **kwargs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"Translator(locale={self._locale!r})"


# ---------------------------------------------------------------------------
# Private utilities
# ---------------------------------------------------------------------------


def _get_nested(data: dict[str, Any], key: str) -> Any:
    """Traverse *data* using a dot-separated *key*."""
    parts = key.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
        if node is None:
            return None
    return node


def _select_plural(value: Any, count: int | None) -> str | None:
    """
    If *value* is a dict with plural keys, select the right form.

    Expected plural dict shape::

        {"zero": "...", "one": "...", "other": "..."}

    Falls back to ``"other"`` when the exact key is absent.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if count is None:
            # No count given — return "other" as default
            return value.get("other") or next(iter(value.values()), None)
        if count == 0 and "zero" in value:
            return value["zero"]
        if count == 1 and "one" in value:
            return value["one"]
        return value.get("other")
    return None


def _interpolate(text: str, **kwargs: Any) -> str:
    """Replace ``{name}`` placeholders with values from *kwargs*."""
    if not kwargs:
        return text
    # Use re.sub so that escaped {{ }} braces are left intact
    def replacer(match: re.Match[str]) -> str:
        return str(kwargs.get(match.group(1), match.group(0)))

    return _PLACEHOLDER_RE.sub(replacer, text)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge *override* into *base* in-place."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _parse_file(path: Path) -> dict[str, Any] | None:
    """
    Parse a JSON, YAML, or YML file and return its contents as a dict.
    Returns ``None`` on parse errors (logs the error).
    """
    suffix = path.suffix.lower()
    try:
        with path.open(encoding="utf-8") as fh:
            if suffix == ".json":
                return json.load(fh)
            if suffix in {".yaml", ".yml"}:
                if not _YAML_AVAILABLE:
                    log.error(
                        "PyYAML is not installed. Install it with: "
                        "pip install discord-i18n[yaml]"
                    )
                    return None
                return _yaml.safe_load(fh) or {}
    except (json.JSONDecodeError, Exception) as exc:
        log.error("Failed to parse %s: %s", path, exc)
    return None


# ---------------------------------------------------------------------------
# Public helper — ezcord-style loader
# ---------------------------------------------------------------------------


def load_languages(
    path: str | os.PathLike[str],
    *,
    encoding: str = "utf-8",
) -> dict[str, dict[str, Any]]:
    """
    Load all YAML (and JSON) locale files from *path* and return a dict in
    **ezcord style**: ``{"en-US": {...}, "de": {...}}``.

    Each file name (without extension) is used as the locale key, e.g.
    ``locales/de.yaml`` → ``"de"``, ``locales/en-US.yaml`` → ``"en-US"``.

    A bare ``en.yaml`` file is automatically expanded to both ``"en-US"`` and
    ``"en-GB"``, mirroring ezcord's behaviour.

    Pass the returned dict directly to :class:`I18n` via the *localizations*
    parameter::

        from discord_i18n import I18n, load_languages

        i18n = I18n(
            default_locale="en-US",
            localizations=load_languages("locales/"),
        )

    Parameters
    ----------
    path:
        Directory containing one locale file per language.
    encoding:
        File encoding. Defaults to ``"utf-8"``.

    Returns
    -------
    dict[str, dict]
        Mapping of locale string → translation data.
    """
    locales_dir = Path(path)
    if not locales_dir.exists():
        raise FileNotFoundError(f"Locales directory not found: {locales_dir!r}")

    result: dict[str, dict[str, Any]] = {}

    for file in sorted(locales_dir.iterdir()):
        if not file.is_file():
            continue
        if file.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue

        locale_key = file.stem
        data = _parse_file(file)
        if data is None:
            continue

        if locale_key in result:
            _deep_merge(result[locale_key], data)
        else:
            result[locale_key] = data

    # Expand bare "en" → en-US + en-GB (ezcord convention)
    if "en" in result:
        en_data = result.pop("en")
        result.setdefault("en-US", {})
        result.setdefault("en-GB", {})
        _deep_merge(result["en-US"], en_data)
        _deep_merge(result["en-GB"], en_data)

    # Expand general-section variables in every locale (ezcord-style)
    for locale_key, data in result.items():
        result[locale_key] = _expand_general(data)

    log.debug("load_languages: loaded %s", sorted(result.keys()))
    return result


# ---------------------------------------------------------------------------
# general-section expansion
# ---------------------------------------------------------------------------

import re as _re

_LOCAL_VAR_RE  = _re.compile(r"\{\.(\w+)\}")   # {.varname}  → local general
_GLOBAL_VAR_RE = _re.compile(r"\{([A-Z_]+)\}") # {VARNAME}   → uppercase global


def _expand_general(data: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve ``general`` variable references throughout *data*.

    * ``{.key}`` is replaced with the value of ``data["general"]["key"]``
      (local, per-file general section).
    * ``{KEY}`` (all-uppercase) is reserved for caller-supplied globals and
      left untouched here.

    The ``general`` section is **kept** in the data so callers can still
    read it; it is simply not translated as a key.
    """
    general: dict[str, str] = {}
    if isinstance(data.get("general"), dict):
        general = {k: str(v) for k, v in data["general"].items()}

    if not general:
        return data

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            def replace_local(m: _re.Match[str]) -> str:
                return general.get(m.group(1), m.group(0))
            return _LOCAL_VAR_RE.sub(replace_local, node)
        if isinstance(node, dict):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    return _walk(data)
