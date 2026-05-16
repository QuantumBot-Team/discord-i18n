"""
Command localization — applies Discord slash-command name / description /
option translations from the same YAML locale files used by I18n.

Attribution
-----------
The ``localize_commands`` / ``_apply_locale`` logic is inspired by
**ezcord** (https://github.com/tibue99/ezcord) and **pycord-i18n**
(https://github.com/Dorukyum/pycord-i18n), both licensed under the
MIT License.

Original ezcord source:
https://github.com/tibue99/ezcord/blob/main/ezcord/internal/language/languages.py

Example
-------
**locales/de.yaml** — add a ``commands`` block to your locale file::

    general:
      bot_name: "MeinBot"

    commands:
      ping:
        name: "ping"               # optional, must be lowercase
        description: "Latenz prüfen"
        options:
          user:
            name: "nutzer"
            description: "Der Ziel-Nutzer"

      # Subcommand group: admin → ban
      admin:
        description: "Admin-Befehle"
        ban:
          description: "Nutzer bannen"
          options:
            member:
              name: "mitglied"
              description: "Das zu bannende Mitglied"

**bot.py** — call ``localize_commands`` after all commands are added,
but before ``tree.sync``::

    import discord
    from discord.ext import commands
    from discord_i18n import load_languages, localize_commands

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    localizations = load_languages("locales/")

    @bot.event
    async def on_ready():
        localize_commands(bot.tree, localizations)
        await bot.tree.sync()
        print(f"Logged in as {bot.user}")

**With Cogs** — load cogs first, then localize::

    # cogs/admin.py
    from discord import app_commands
    from discord.ext import commands

    class AdminCog(commands.Cog):
        def __init__(self, bot):
            self.bot = bot

        @app_commands.command(name="ban", description="Ban a user")
        async def ban(self, interaction: discord.Interaction, member: discord.Member):
            await interaction.response.send_message(f"Banned {member}")

    # bot.py
    import asyncio
    import discord
    from discord.ext import commands
    from discord_i18n import load_languages, localize_commands

    async def main():
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        localizations = load_languages("locales/")

        async with bot:
            await bot.load_extension("cogs.admin")   # load cogs FIRST
            localize_commands(bot.tree, localizations) # THEN localize
            await bot.start("TOKEN")

    asyncio.run(main())
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def localize_commands(
    tree: Any,
    localizations: dict[str, dict[str, Any]],
    *,
    default_locale: str = "en-US",
) -> None:
    """
    Apply name / description / option translations to all commands in *tree*.

    The translation data is read from the ``commands`` key in each locale dict
    inside *localizations* (the same dict returned by :func:`load_languages`).

    Parameters
    ----------
    tree:
        A ``discord.app_commands.CommandTree`` instance.
    localizations:
        Locale dict as returned by :func:`load_languages`, e.g.
        ``{"en-US": {...}, "de": {...}}``.
    default_locale:
        The locale whose values are used to set the *canonical* name and
        description on the command object itself (not just the localizations
        mapping).  Defaults to ``"en-US"``.
    """
    try:
        import discord  # noqa: F401 – presence check
        from discord import app_commands
    except ImportError:
        log.error(
            "discord.py is required for localize_commands. "
            "Install it with: pip install discord-i18n[discord]"
        )
        return

    # Collect every command in the tree (flat list, includes subcommands)
    all_commands: list[app_commands.Command | app_commands.Group] = list(
        tree.walk_commands()
    )

    for locale, data in localizations.items():
        cmd_data: dict[str, Any] = data.get("commands", {})
        if not cmd_data:
            continue

        for cmd in all_commands:
            _apply_locale(cmd, locale, cmd_data, default_locale)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_locale(
    cmd: Any,
    locale: str,
    cmd_data: dict[str, Any],
    default_locale: str,
) -> None:
    """Apply a single locale to a single command / group."""
    from discord import app_commands

    # For nested commands (subcommands), walk the full qualified name path.
    # e.g. "admin ban" → look up cmd_data["admin"]["ban"]
    parts = cmd.qualified_name.split()
    node: Any = cmd_data
    for part in parts:
        if not isinstance(node, dict):
            return
        node = node.get(part)
        if node is None:
            return

    if not isinstance(node, dict):
        return

    loc = str(locale)

    # --- name ---
    if name := node.get("name"):
        _set_localization(cmd, "name_localizations", loc, name)
        if loc == default_locale:
            cmd.name = name

    # --- description (only on Command, not Group in discord.py) ---
    if description := node.get("description"):
        _set_localization(cmd, "description_localizations", loc, description)
        if loc == default_locale:
            cmd.description = description

    # --- options (only on Command) ---
    if isinstance(cmd, app_commands.Command):
        options_data: dict[str, Any] = node.get("options", {})
        for param in cmd._params.values():  # noqa: SLF001
            opt_data = options_data.get(param.name)
            if not opt_data:
                continue
            if opt_name := opt_data.get("name"):
                _set_localization(param, "name_localizations", loc, opt_name)
                if loc == default_locale:
                    param.name = opt_name
            if opt_desc := opt_data.get("description"):
                _set_localization(param, "description_localizations", loc, opt_desc)
                if loc == default_locale:
                    param.description = opt_desc


def _set_localization(obj: Any, attr: str, locale: str, value: str) -> None:
    """
    Add *value* for *locale* to the ``name_localizations`` or
    ``description_localizations`` dict on *obj*.

    Creates the dict if it doesn't exist yet (discord.py uses ``MISSING``
    as the sentinel for unset localizations).
    """
    try:
        from discord.utils import MISSING
    except ImportError:
        MISSING = None  # type: ignore[assignment]

    current = getattr(obj, attr, MISSING)
    if current is MISSING or current is None:
        setattr(obj, attr, {locale: value})
    else:
        current[locale] = value
