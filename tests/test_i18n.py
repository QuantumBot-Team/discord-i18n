"""
Tests for discord-i18n.

Run with:  pytest
"""

from __future__ import annotations

import pytest

from discord_i18n import I18n, Locale
from discord_i18n.translator import TranslationNotFoundError, _interpolate, _select_plural


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TRANSLATIONS_EN = {
    "ping": {"response": "Pong! Latency: {latency}ms"},
    "greet": {"hello": "Hello, {name}!"},
    "errors": {
        "cooldown": {
            "zero": "No cooldown.",
            "one": "Wait {seconds} second.",
            "other": "Wait {seconds} seconds.",
        }
    },
}

TRANSLATIONS_DE = {
    "ping": {"response": "Pong! Latenz: {latency}ms"},
    "greet": {"hello": "Hallo, {name}!"},
}


@pytest.fixture
def i18n() -> I18n:
    inst = I18n(default_locale="en-US", missing_key_mode="key")
    inst.add_locale("en-US", TRANSLATIONS_EN)
    inst.add_locale("de", TRANSLATIONS_DE)
    return inst


# ---------------------------------------------------------------------------
# Locale tests
# ---------------------------------------------------------------------------


def test_locale_language_subtag():
    assert Locale.from_str("en-US").language == "en"
    assert Locale.from_str("zh-CN").language == "zh"
    assert Locale.from_str("de").language == "de"


def test_locale_fallback_chain_with_region():
    chain = Locale.from_str("en-US").fallback_chain()
    assert chain == ["en-US", "en"]


def test_locale_fallback_chain_without_region():
    chain = Locale.from_str("de").fallback_chain()
    assert chain == ["de"]


def test_locale_is_discord_locale():
    assert Locale.from_str("de").is_discord_locale
    assert not Locale.from_str("xx-FAKE").is_discord_locale


# ---------------------------------------------------------------------------
# I18n / Translator tests
# ---------------------------------------------------------------------------


def test_basic_translation(i18n: I18n):
    assert i18n.t("greet.hello", locale="en-US", name="Alice") == "Hello, Alice!"


def test_german_translation(i18n: I18n):
    assert i18n.t("greet.hello", locale="de", name="Bob") == "Hallo, Bob!"


def test_fallback_to_default(i18n: I18n):
    # "errors.cooldown" is only in en-US; should fall back from "de"
    result = i18n.t("errors.cooldown", locale="de", count=3, seconds=3)
    assert result == "Wait 3 seconds."


def test_fallback_chain_en_gb(i18n: I18n):
    # en-GB is not loaded; should fall back to en-US via default_locale
    result = i18n.t("greet.hello", locale="en-GB", name="Charlie")
    assert result == "Hello, Charlie!"


def test_missing_key_returns_key(i18n: I18n):
    assert i18n.t("does.not.exist") == "does.not.exist"


def test_missing_key_raises():
    inst = I18n(default_locale="en-US", missing_key_mode="raise")
    inst.add_locale("en-US", TRANSLATIONS_EN)
    with pytest.raises(TranslationNotFoundError):
        inst.t("no.such.key")


def test_missing_key_returns_empty():
    inst = I18n(default_locale="en-US", missing_key_mode="empty")
    inst.add_locale("en-US", TRANSLATIONS_EN)
    assert inst.t("no.such.key") == ""


def test_plural_one(i18n: I18n):
    result = i18n.t("errors.cooldown", locale="en-US", count=1, seconds=1)
    assert result == "Wait 1 second."


def test_plural_zero(i18n: I18n):
    result = i18n.t("errors.cooldown", locale="en-US", count=0, seconds=0)
    assert result == "No cooldown."


def test_plural_other(i18n: I18n):
    result = i18n.t("errors.cooldown", locale="en-US", count=5, seconds=5)
    assert result == "Wait 5 seconds."


def test_translator_callable(i18n: I18n):
    t = i18n.get_translator("de")
    assert t.locale == "de"
    assert t("greet.hello", name="Welt") == "Hallo, Welt!"


def test_available_locales(i18n: I18n):
    assert set(i18n.available_locales) == {"en-US", "de"}


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------


def test_interpolate_basic():
    assert _interpolate("Hello, {name}!", name="World") == "Hello, World!"


def test_interpolate_escaped_braces():
    assert _interpolate("{{not a placeholder}}") == "{{not a placeholder}}"


def test_interpolate_missing_placeholder():
    # Unknown placeholder is left as-is
    assert _interpolate("Hi {unknown}") == "Hi {unknown}"


def test_select_plural_string():
    assert _select_plural("hello", None) == "hello"
    assert _select_plural("hello", 5) == "hello"


def test_select_plural_no_count():
    d = {"one": "item", "other": "items"}
    assert _select_plural(d, None) == "items"


# ---------------------------------------------------------------------------
# Deep-merge test
# ---------------------------------------------------------------------------


def test_add_locale_merges(i18n: I18n):
    i18n.add_locale("en-US", {"extra": {"key": "value"}})
    assert i18n.t("extra.key", locale="en-US") == "value"
    # original keys still intact
    assert i18n.t("greet.hello", locale="en-US", name="X") == "Hello, X!"
