"""
Helpers and decorators that integrate discord-i18n with discord.py.

Attribution
-----------
``locale_from_interaction`` / ``locale_from_ctx`` locale-extraction logic
is inspired by **ezcord** (https://github.com/tibue99/ezcord),
licensed under the MIT License (Copyright © tibue99).

Original source: https://github.com/tibue99/ezcord/blob/main/ezcord/i18n.py
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import TYPE_CHECKING, Any, Callable

from .translator import I18n, Translator

if TYPE_CHECKING:
    pass  # keep imports optional at runtime

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locale extraction helpers
# ---------------------------------------------------------------------------


def locale_from_interaction(interaction: Any) -> str:
    """
    Return the locale string for a :class:`discord.Interaction`.

    Tries (in order):

    1. ``interaction.locale`` (user locale — set by Discord client)
    2. ``interaction.guild_locale`` (server locale)
    3. Falls back to ``"en-US"``
    """
    locale: str | None = getattr(interaction, "locale", None)
    if locale is not None:
        # discord.py ≥ 2.0 returns a ``discord.Locale`` enum; convert to str
        return str(locale)

    guild_locale: str | None = getattr(interaction, "guild_locale", None)
    if guild_locale is not None:
        return str(guild_locale)

    return "en-US"


def locale_from_ctx(ctx: Any, fallback: str = "en-US") -> str:
    """
    Return the locale string for a :class:`~discord.ext.commands.Context`.

    Prefix commands do not carry a locale in the Discord protocol, so this
    helper looks for a ``locale`` attribute you may have stored on the guild or
    the bot itself (e.g. via a database).  Falls back to *fallback* otherwise.

    Lookup order:

    1. ``ctx.locale`` (custom attribute)
    2. ``ctx.guild.locale`` (custom attribute on the guild object)
    3. ``ctx.bot.default_locale`` (custom attribute on the bot)
    4. *fallback* argument (``"en-US"`` by default)
    """
    for path in ("locale", "guild.locale", "bot.default_locale"):
        obj: Any = ctx
        try:
            for attr in path.split("."):
                obj = getattr(obj, attr)
            if isinstance(obj, str) and obj:
                return obj
        except AttributeError:
            continue

    return fallback


# ---------------------------------------------------------------------------
# @use_locale decorator
# ---------------------------------------------------------------------------


def use_locale(i18n: I18n, *, param: str = "t") -> Callable[..., Any]:
    """
    Decorator factory that injects a :class:`Translator` into a slash-command
    callback.

    The :class:`~discord.Interaction` must be the **first** positional argument
    of the decorated function (``self`` excluded for methods).

    Parameters
    ----------
    i18n:
        The :class:`I18n` instance to use for translation.
    param:
        Name of the keyword argument that will receive the
        :class:`Translator`.  Defaults to ``"t"``.

    Example
    -------
    ::

        @tree.command()
        @use_locale(i18n)
        async def ping(interaction: discord.Interaction, t: Translator):
            await interaction.response.send_message(t("ping.response"))
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        sig = inspect.signature(func)
        params = list(sig.parameters.keys())

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Find the Interaction argument
            interaction = _find_interaction(args, kwargs, params)

            if interaction is not None:
                locale_str = locale_from_interaction(interaction)
            else:
                log.warning(
                    "use_locale: could not find discord.Interaction in %s; "
                    "using default locale.",
                    func.__qualname__,
                )
                locale_str = str(i18n._default_locale)

            kwargs[param] = i18n.get_translator(locale_str)
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def _find_interaction(args: tuple[Any, ...], kwargs: dict[str, Any], params: list[str]) -> Any:
    """Return the first argument that looks like a discord.Interaction."""
    # Check kwargs first
    for name, value in kwargs.items():
        if _is_interaction(value):
            return value

    # Walk positional args, matched by position in the signature
    for i, value in enumerate(args):
        if _is_interaction(value):
            return value

    return None


def _is_interaction(obj: Any) -> bool:
    """
    Duck-type check: does *obj* look like a ``discord.Interaction``?

    We avoid importing discord at module level so that the package stays
    importable even without discord.py installed (e.g. in tests).
    """
    return (
        hasattr(obj, "response")
        and hasattr(obj, "locale")
        and callable(getattr(obj, "response", None) or (lambda: None))
    )
