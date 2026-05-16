"""
Locale dataclass — wraps a BCP-47 locale string and provides helpers.
"""

from __future__ import annotations

from dataclasses import dataclass


# Discord locale strings as of 2024
DISCORD_LOCALES: frozenset[str] = frozenset(
    {
        "id",       # Indonesian
        "da",       # Danish
        "de",       # German
        "en-GB",    # English (UK)
        "en-US",    # English (US)
        "es-ES",    # Spanish (Spain)
        "es-419",   # Spanish (LATAM)
        "fr",       # French
        "hr",       # Croatian
        "it",       # Italian
        "lt",       # Lithuanian
        "hu",       # Hungarian
        "nl",       # Dutch
        "no",       # Norwegian
        "pl",       # Polish
        "pt-BR",    # Portuguese (Brazil)
        "ro",       # Romanian
        "fi",       # Finnish
        "sv-SE",    # Swedish
        "vi",       # Vietnamese
        "tr",       # Turkish
        "cs",       # Czech
        "el",       # Greek
        "bg",       # Bulgarian
        "ru",       # Russian
        "uk",       # Ukrainian
        "hi",       # Hindi
        "th",       # Thai
        "zh-CN",    # Chinese (Simplified)
        "ja",       # Japanese
        "zh-TW",    # Chinese (Traditional)
        "ko",       # Korean
    }
)


@dataclass(frozen=True)
class Locale:
    """Represents a BCP-47 locale string used by Discord."""

    value: str

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_str(cls, value: str) -> "Locale":
        return cls(value=value)

    @classmethod
    def default(cls) -> "Locale":
        return cls(value="en-US")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def language(self) -> str:
        """Return the primary language subtag (e.g. 'en' from 'en-US')."""
        return self.value.split("-")[0]

    @property
    def is_discord_locale(self) -> bool:
        return self.value in DISCORD_LOCALES

    def fallback_chain(self) -> list[str]:
        """
        Return a list of locale strings to try in order.

        Example: 'en-US' → ['en-US', 'en']
        """
        chain: list[str] = [self.value]
        if "-" in self.value or "_" in self.value:
            chain.append(self.language)
        return chain

    def __str__(self) -> str:
        return self.value
