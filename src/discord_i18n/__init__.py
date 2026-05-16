"""
discord-i18n — Internationalization library for discord.py bots.

This library is inspired by ezcord (https://github.com/tibue99/ezcord)
by tibue99, licensed under the MIT License.
See NOTICE for full third-party attributions.
"""

from .translator import I18n, Translator, load_languages
from .locale import Locale
from .decorators import locale_from_interaction, locale_from_ctx
from .cmd_localizer import localize_commands
from .utils import check_missing_keys, I18nCog, I18nView, I18nModal

__all__ = [
    "I18n",
    "Translator",
    "Locale",
    "load_languages",
    "locale_from_interaction",
    "locale_from_ctx",
    "localize_commands",
    "check_missing_keys",
    "I18nCog",
    "I18nView",
    "I18nModal",
]

__version__ = "1.0.0"
