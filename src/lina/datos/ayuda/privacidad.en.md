# Privacy: what leaves your computer and what doesn't

Lina has no telemetry: she sends no statistics or usage data to anyone. The only thing that leaves your computer is what is needed to answer you.

## What is sent to the AI (Gemini, from Google, unless you change provider)

- **What you say, as text.** Your voice is turned into text on your own computer (Whisper); the audio is not sent anywhere.
- **The current conversation** (your latest questions and my answers), so we can keep talking about the same thing.
- **The name of the active window and its program**, to know what you are talking about.
- **Screenshots of your screen, only if you allow it** (`lina privacidad si`) and only when needed: in a game, if you talk about what you see, or if the AI asks for it.
  Never with **private mode** on, nor with **sensitive** windows (banks, billing, password managers…), nor while you haven't decided.
- **The result of the commands and tools** the AI uses to help you (for example, the list of installed programs or the text of a page you ask it to read).
- If you have set a **Tavily** key, the text of the web searches you make.

## What is NOT sent

- Your voice recordings.
- Your keys and passwords (the system keyring keeps them; the AI can't read them and they are not printed in the log).
- Your files, unless you ask for something that requires reading one (then only what is read for that task).
- Screenshots in private mode, with sensitive windows or without your permission.

## What Google says about what it receives

With the **free** key, according to Google's current terms, what is sent may be used to improve its products and may be reviewed by people; with a **paid** key it is not. Check the Gemini API terms before sending anything you don't want to share. If you work with confidential information, use the paid key, a provider that meets what your company requires, or private mode.

## What Lina stores on your computer

| What | Where | How to delete it |
|---|---|---|
| Change journal and copies for undoing | `~/.local/share/lina/diario` | `lina olvidar diario` |
| Action log (commands run) | `~/.local/state/lina/acciones.log` (rotates itself at ~1 MB) | `lina olvidar acciones` |
| Learned recipes (what you already asked me that went well: the phrase, the steps and how it was checked; never passwords) | `~/.local/share/lina/recetas.json` | `lina olvidar recetas` or `lina recetas borrar todas` |
| Timings of each request (numbers only, never what you say; `lina tiempos` summarises them) | `~/.local/state/lina/tiempos.jsonl` (trims itself at ~200 KB) | `lina olvidar tiempos` |
| System log (what you say and I answer, unless you turn it off) | `journalctl --user -u lina` | `lina olvidar registro` |

So that what you say and I answer doesn't stay in the log: `lina config poner privacidad.registrar_preguntas false`.
Temporary recordings and screenshots live in your session's runtime folder (memory) and disappear when you log out.

## How to decide

```
lina privacidad          explains it and asks you
lina privacidad si       I allow screenshots when needed
lina privacidad no       never screenshots
```

The AI can't change this decision on its own: you make it. If you left it on «preguntar» and, for what you ask, Lina needs to see your screen, she will ask you
(explaining that the screenshot goes to Google) and it only turns on if you confirm by pressing the shortcut; hands-free voice doesn't count. If you said «no», she
doesn't insist: only you change it, in a terminal.
