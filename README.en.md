# Lina

[Español](README.md) · English

A voice assistant for the Linux desktop, designed first for Spanish (English is experimental). You talk to her («Hey Lina, …») or press a shortcut, and she understands
what you want, does it on your computer (open programs, adjust the system, manage windows, search, write documents…) and answers you out loud.

> **Status: early beta (0.1).** It works fully on Arch Linux and derivatives with KDE Plasma (Wayland). The core is also tested on Debian/Ubuntu, Fedora and openSUSE;
> GNOME, Cinnamon, XFCE, sway and Hyprland are supported but not yet tested on real machines. The detailed documentation is in Spanish (see [docs/](docs/)); this page and
> the program's own messages are available in English.

## What makes it different

- **It understands intent, not fixed phrases.** Ask for things in your own words.
- **It works out how to do things itself** and remembers what it has verified works («recipes»).
- **Autonomous, but with brakes.** Dangerous things (really deleting, touching disks or boot, installing outside software…) are only confirmed with the
  keyboard shortcut, never by voice. Everything that changes is kept in a journal and can be undone.
- **Your data is yours.** No telemetry. Screenshots are only sent with your consent, and there is a private mode.
- **Cheap.** It works with the free Gemini key; a paid key is optional and has a monthly cap.
- **Not tied to one AI.** Gemini by default, switchable to Anthropic, OpenAI or any compatible service (OpenRouter, Groq, Ollama on your machine, your company's server) with `lina ia`.

## Installation (summary)

```sh
git clone https://github.com/daniestu/lina.git
cd lina
./install.sh
```

The installer shows you each step, creates the keyboard shortcut and the service, and ends with `lina bienvenida` (the welcome), which guides you through entering
your (free) Gemini key, testing the microphone and deciding Lina's freedom and privacy. Afterwards: `lina doctor` to check everything is fine and `lina update`
to update. More detail in [docs/instalacion.md](docs/instalacion.md).

## Using English

```sh
lina config poner asistente.idioma en
systemctl --user restart lina
```

Then she listens and speaks English, and the terminal commands show their messages in English. The command names themselves (`lina config`, `lina voz`…) stay as they are.
English is experimental: speech recognition, the voices and the translations still need testing by native speakers.

## Settings

Everything lives in a single file, `~/.config/lina/config.toml`, and is changed with `lina config` (applies without restarting):

```sh
lina config                          # see all settings
lina config poner asistente.nombre Jarvis
lina config perfil prudente          # autonomo (default), equilibrado or prudente
lina voz                             # choose another voice
```

## Privacy and permissions

```sh
lina privacidad       # what is sent to the AI and what isn't; you decide whether screenshots are sent
lina privilegios      # what administrator permissions Lina has (none by default)
lina olvidar          # delete what she keeps about you
```

No telemetry. Screenshots aren't sent until you allow it, and your administrator password never passes through Lina. Details and threat model in
[docs/seguridad.md](docs/seguridad.md) (Spanish).

## License

[GNU AGPL-3.0 or later](LICENSE). It is open source: you can use, study, modify and share it. If you share a modified version, or offer it as a service over the
Internet, you must publish your code under the same license and keep the copyright notices. The name «Lina» and its logo are not covered by the license: see
[TRADEMARKS.md](TRADEMARKS.md).
