"""
Developer utilities for discord-i18n.

Attribution
-----------
``check_missing_keys`` is inspired by ezcord's internal
``I18N._check_localizations`` (https://github.com/tibue99/ezcord),
licensed under the MIT License (Copyright © tibue99).

Functions
---------
check_missing_keys(i18n)
    Find translation keys that exist in the default locale but are absent in
    one or more other locales.  Useful on bot startup or in CI.

Classes
-------
I18nCog
    A ``discord.ext.commands.Cog`` mixin that exposes ``self.t(key, interaction_or_locale, ...)``
    so you don't have to carry the ``I18n`` instance around manually.
I18nView
    A ``discord.ui.View`` mixin with the same built-in ``self.t()``.
I18nModal
    A ``discord.ui.Modal`` mixin with the same built-in ``self.t()``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .translator import I18n

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# check_missing_keys
# ---------------------------------------------------------------------------


def check_missing_keys(
    i18n: "I18n",
    *,
    warn: bool = True,
) -> dict[str, list[str]]:
    """
    Compare every loaded locale against the default locale and report keys
    that are present in the default but missing elsewhere.

    Like ezcord's internal ``_check_localizations``, but public and returns
    structured data instead of just logging.

    Parameters
    ----------
    i18n:
        The :class:`~discord_i18n.I18n` instance to inspect.
    warn:
        When ``True`` (default), log a ``WARNING`` for every locale that has
        missing keys.

    Returns
    -------
    dict[str, list[str]]
        ``{locale: [missing_dot_key, ...]}`` — empty dict means all good.

    Example
    -------
    ::

        from discord_i18n import check_missing_keys

        missing = check_missing_keys(i18n)
        # {"de": ["errors.cooldown.zero"], "fr": ["ping.description"]}
    """
    default = str(i18n._default_locale)
    reference = i18n._data.get(default, {})

    if not reference:
        log.warning(
            "check_missing_keys: default locale %r not found in loaded data.", default
        )
        return {}

    result: dict[str, list[str]] = {}

    for locale, data in i18n._data.items():
        if locale == default:
            continue
        missing = _find_missing(reference, data, "")
        if missing:
            result[locale] = missing
            if warn:
                log.warning(
                    "Locale %r is missing %d key(s) from %r: %s",
                    locale,
                    len(missing),
                    default,
                    missing,
                )

    return result


def _find_missing(
    reference: dict[str, Any],
    current: dict[str, Any],
    prefix: str,
) -> list[str]:
    """Recursively collect dot-paths present in *reference* but absent in *current*."""
    missing: list[str] = []
    for key, value in reference.items():
        path = f"{prefix}.{key}".lstrip(".")
        if key not in current:
            missing.append(path)
        elif isinstance(value, dict) and isinstance(current.get(key), dict):
            missing.extend(_find_missing(value, current[key], path))
    return missing


# ---------------------------------------------------------------------------
# I18nCog
# ---------------------------------------------------------------------------


class I18nCog:
    """
    Mixin for ``discord.ext.commands.Cog`` subclasses.

    Attach an :class:`~discord_i18n.I18n` instance once and use
    ``self.t(key, interaction_or_locale, ...)`` everywhere in the cog without
    repeating the import.

    Usage
    -----
    ::

        from discord.ext import commands
        from discord_i18n import I18n, load_languages, I18nCog

        i18n = I18n(default_locale="en-US", localizations=load_languages("locales/"))


        class MyCog(I18nCog, commands.Cog, i18n=i18n):
            @app_commands.command()
            async def ping(self, interaction: discord.Interaction):
                await interaction.response.send_message(
                    self.t("ping.response", interaction, latency=round(self.bot.latency * 1000))
                )

    Alternatively set ``i18n`` after class creation::

        class MyCog(I18nCog, commands.Cog):
            pass

        MyCog.set_i18n(i18n)

    Parameters (class keyword)
    --------------------------
    i18n:
        The :class:`~discord_i18n.I18n` instance to bind to this cog class.
    """

    _i18n: "I18n | None" = None

    def __init_subclass__(cls, i18n: "I18n | None" = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if i18n is not None:
            cls._i18n = i18n

    @classmethod
    def set_i18n(cls, i18n: "I18n") -> None:
        """Bind an :class:`~discord_i18n.I18n` instance to this cog class."""
        cls._i18n = i18n

    def t(
        self,
        key: str,
        locale_source: Any = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Translate *key* using the locale extracted from *locale_source*.

        Parameters
        ----------
        key:
            Dot-separated translation key, e.g. ``"ping.response"``.
        locale_source:
            A ``discord.Interaction``, a locale string, or ``None`` to use
            the default locale.
        count:
            Enables plural selection when given.
        **kwargs:
            Placeholder values for interpolation.
        """
        if self._i18n is None:
            raise RuntimeError(
                f"{type(self).__name__}: no I18n instance bound. "
                "Pass i18n= as a class keyword or call set_i18n()."
            )

        from .decorators import locale_from_interaction

        if locale_source is None:
            locale = str(self._i18n._default_locale)
        elif isinstance(locale_source, str):
            locale = locale_source
        else:
            # duck-type: Interaction, ApplicationContext, …
            locale = locale_from_interaction(locale_source)

        return self._i18n.t(key, locale=locale, count=count, **kwargs)


# ---------------------------------------------------------------------------
# I18nView / I18nModal
# ---------------------------------------------------------------------------

class _I18nUIMixin:
    """
    Shared mixin for :class:`I18nView` and :class:`I18nModal`.

    Provides ``self.t(key, interaction_or_locale, ...)`` and
    ``self.set_i18n(i18n)`` in the same way as :class:`I18nCog`.
    """

    _i18n: "I18n | None" = None

    def __init_subclass__(cls, i18n: "I18n | None" = None, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if i18n is not None:
            cls._i18n = i18n

    @classmethod
    def set_i18n(cls, i18n: "I18n") -> None:
        """Bind an :class:`~discord_i18n.I18n` instance to this class."""
        cls._i18n = i18n

    def t(
        self,
        key: str,
        locale_source: Any = None,
        count: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Translate *key* — same signature as :meth:`I18nCog.t`."""
        if self._i18n is None:
            raise RuntimeError(
                f"{type(self).__name__}: no I18n instance bound. "
                "Pass i18n= as a class keyword or call set_i18n()."
            )

        from .decorators import locale_from_interaction

        if locale_source is None:
            locale = str(self._i18n._default_locale)
        elif isinstance(locale_source, str):
            locale = locale_source
        else:
            locale = locale_from_interaction(locale_source)

        return self._i18n.t(key, locale=locale, count=count, **kwargs)


class I18nView(_I18nUIMixin):
    """
    A ``discord.ui.View`` subclass with built-in ``self.t()`` translation.

    Usage
    -----
    ::

        import discord
        from discord_i18n import I18n, load_languages, I18nView

        i18n = I18n(default_locale="en-US", localizations=load_languages("locales/"))


        class ConfirmView(I18nView, discord.ui.View, i18n=i18n):
            def __init__(self, interaction: discord.Interaction):
                super().__init__(timeout=60)
                self._locale = interaction.locale

            @discord.ui.button(label="✅")
            async def confirm(self, interaction: discord.Interaction, button):
                await interaction.response.send_message(
                    self.t("confirm.yes", self._locale)
                )

            @discord.ui.button(label="❌")
            async def cancel(self, interaction: discord.Interaction, button):
                await interaction.response.send_message(
                    self.t("confirm.no", self._locale)
                )
    """


class I18nModal(_I18nUIMixin):
    """
    A ``discord.ui.Modal`` subclass with built-in ``self.t()`` translation.

    Usage
    -----
    ::

        import discord
        from discord_i18n import I18n, load_languages, I18nModal

        i18n = I18n(default_locale="en-US", localizations=load_languages("locales/"))


        class FeedbackModal(I18nModal, discord.ui.Modal, i18n=i18n):
            feedback = discord.ui.TextInput(label="Feedback")

            def __init__(self, interaction: discord.Interaction):
                title = i18n.t("feedback.title", locale=interaction.locale)
                super().__init__(title=title)
                self._locale = str(interaction.locale)

            async def on_submit(self, interaction: discord.Interaction):
                await interaction.response.send_message(
                    self.t("feedback.thanks", self._locale)
                )
    """
