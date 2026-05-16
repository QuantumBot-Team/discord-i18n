# discord-i18n

Internationalization (i18n) library for **discord.py** bots — inspired by [ezcord](https://github.com/tibue99/ezcord).

* One YAML (or JSON) file per locale — same layout as ezcord
* `load_languages()` helper mirrors ezcord's style
* Pluralization (`one` / `other` / `zero`)
* `{placeholder}` interpolation + `{.general}` variable expansion
* Fallback locale chain (`en-US` → `en`)
* `@use_locale` decorator injects a bound `Translator` into slash-command callbacks
* `I18nCog` mixin — built-in `self.t()` in every cog
* `check_missing_keys()` — catch missing translations at startup or in CI
* `localize_commands()` — translate command names, descriptions, and options
* Zero required runtime dependencies — `discord.py` and `PyYAML` are optional extras

---

## Installation

```bash
pip install discord-i18n          # core only
pip install discord-i18n[yaml]    # + PyYAML (recommended)
pip install discord-i18n[discord] # + discord.py
```

---

## Quick start

### 1. Create your locale files

```
locales/
├── en-US.yaml
├── de.yaml
└── fr.yaml
```

**`locales/en-US.yaml`** (ezcord-style YAML):

```yaml
ping:
  response: "Pong! Latency: {latency}ms"

greet:
  hello: "Hello, {name}!"

errors:
  cooldown:
    one:   "Please wait {seconds} second."
    other: "Please wait {seconds} seconds."
```

**`locales/de.yaml`**:

```yaml
ping:
  response: "Pong! Latenz: {latency}ms"

greet:
  hello: "Hallo, {name}!"

errors:
  cooldown:
    one:   "Bitte warte {seconds} Sekunde."
    other: "Bitte warte {seconds} Sekunden."
```

### 2. Set up the bot

```python
import discord
from discord import app_commands
from discord_i18n import I18n, load_languages, use_locale

# ezcord-style: load all YAML files from the locales/ folder
i18n = I18n(
    default_locale="en-US",
    localizations=load_languages("locales/"),
)

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()
```

### 3. Use in slash commands

#### With the `@use_locale` decorator

```python
from discord_i18n import use_locale, Translator

@bot.tree.command()
@use_locale(i18n)
async def ping(interaction: discord.Interaction, t: Translator):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(t("ping.response", latency=latency))
```

#### Manually

```python
from discord_i18n import locale_from_interaction

@bot.tree.command()
async def greet(interaction: discord.Interaction):
    t = i18n.get_translator(locale_from_interaction(interaction))
    await interaction.response.send_message(t("greet.hello", name=interaction.user.name))
```

#### Pluralization

```python
@bot.tree.command()
@use_locale(i18n)
async def cooldown(interaction: discord.Interaction, t: Translator):
    seconds = 5
    msg = t("errors.cooldown", count=seconds, seconds=seconds)
    await interaction.response.send_message(msg)
```

---

## YAML file structure

Keys can be nested (ezcord style) **or** dot-separated:

```yaml
# Nested (ezcord style)
commands:
  ping:
    response: "Pong!"

# Dot-notation also works when calling t()
# i18n.t("commands.ping.response")
```

### Pluralization

Use a mapping with `one`, `other`, and optionally `zero`:

```yaml
items:
  count:
    zero:  "No items"
    one:   "{count} item"
    other: "{count} items"
```

```python
t("items.count", count=0)   # → "No items"
t("items.count", count=1)   # → "1 item"
t("items.count", count=5)   # → "5 items"
```

### `general` section

Values in `general` are available via `{.key}` anywhere in the **same file** — they are automatically expanded when the locale is loaded (no extra call needed):

```yaml
general:
  support_server: "https://discord.gg/example"
  bot_name: "MyBot"

errors:
  help: "Join our support server: {.support_server}"
  footer: "Powered by {.bot_name}"
```

> The `general` section stays in the data so you can still look it up; its values are simply pre-expanded into every string that references them.

---

## API reference

### `load_languages(path)`

Loads all `.yaml` / `.yml` / `.json` files from *path* and returns a
`{"locale": {...}}` dict ready to pass to `I18n`.

```python
localizations = load_languages("locales/")
# → {"en-US": {...}, "de": {...}, "fr": {...}}
```

A bare `en.yaml` is automatically expanded to both `en-US` **and** `en-GB`
(same as ezcord).

---

### `I18n`

```python
I18n(
    default_locale="en-US",       # fallback when no locale is found
    localizations=load_languages("locales/"),  # ezcord-style pre-built dict
    # OR: locales_dir="locales/",  # load from directory (JSON + YAML)
    fallback_locale="en-US",      # secondary fallback
    missing_key_mode="key",       # "key" | "empty" | "raise"
)
```

| Method | Description |
|---|---|
| `i18n.t(key, locale=..., count=..., **kwargs)` | Translate a key |
| `i18n.get_translator(locale)` | Return a bound `Translator` callable |
| `i18n.load()` | Load/reload from `locales_dir` |
| `i18n.add_locale(locale, data)` | Register translations programmatically |
| `i18n.available_locales` | List of loaded locale strings |

---

### `Translator`

A callable returned by `i18n.get_translator(locale)`:

```python
t = i18n.get_translator("de")
t("greet.hello", name="Welt")   # → "Hallo, Welt!"
t("errors.cooldown", count=3, seconds=3)
```

---

### `@use_locale(i18n)`

Decorator that resolves the locale from the `discord.Interaction` and injects
a bound `Translator` as the `t` parameter:

```python
@tree.command()
@use_locale(i18n)
async def my_cmd(interaction: discord.Interaction, t: Translator):
    await interaction.response.send_message(t("some.key"))
```

---

### `locale_from_interaction(interaction)` / `locale_from_ctx(ctx)`

Extract the locale string from an `Interaction` or a prefix-command `Context`.

---

## `I18nCog` — built-in translation in every Cog

`I18nCog` is a mixin for `discord.ext.commands.Cog` that binds an `I18n` instance once and exposes `self.t()` everywhere in the cog:

```python
from discord.ext import commands
from discord_i18n import I18n, load_languages, I18nCog

i18n = I18n(default_locale="en-US", localizations=load_languages("locales/"))


class GreetCog(I18nCog, commands.Cog, i18n=i18n):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    async def greet(self, interaction: discord.Interaction):
        # locale is resolved automatically from the Interaction
        msg = self.t("greet.hello", interaction, name=interaction.user.name)
        await interaction.response.send_message(msg)
```

You can also set the instance after class definition (useful in large projects):

```python
class GreetCog(I18nCog, commands.Cog):
    ...

GreetCog.set_i18n(i18n)
```

---

## `check_missing_keys` — catch missing translations early

Call this on startup or in your test suite to find keys that exist in the default locale but are missing in other languages:

```python
from discord_i18n import check_missing_keys

missing = check_missing_keys(i18n)
# {"de": ["errors.cooldown.zero"], "fr": ["ping.description"]}

if missing:
    print("Missing translations:", missing)
```

By default a `WARNING` is also logged for every affected locale. Pass `warn=False` to suppress logs and only use the return value.

---

## Command localization

Discord lets you translate slash-command **names**, **descriptions**, and **option names/descriptions** per locale. `discord-i18n` applies these from the same YAML files.

### 1. Add a `commands` section to your locale files

```yaml
# locales/de.yaml
commands:
  ping:
    name: "ping"
    description: "Latenz des Bots prüfen"

  greet:
    name: "begrüßen"
    description: "Eine Begrüßung senden"
    options:
      name:
        name: "name"
        description: "Der zu begrüßende Nutzer"

  # Subcommand group
  admin:
    description: "Admin-Befehle"
    ban:
      description: "Einen Nutzer bannen"
      options:
        user:
          name: "nutzer"
          description: "Der zu bannende Nutzer"
```

### 2. Call `localize_commands` before syncing

```python
from discord_i18n import load_languages, localize_commands

localizations = load_languages("locales/")

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        localize_commands(self.tree, localizations)  # ← before sync
        await self.tree.sync()
```

`localize_commands` sets `name_localizations` and `description_localizations` on every command / subcommand / option it finds in the `commands` block. The `default_locale` (default `"en-US"`) values are also applied directly to the command object.

