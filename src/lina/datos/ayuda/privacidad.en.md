# Privacy: what leaves your computer and what doesn't

Lina has no telemetry: she sends no statistics or usage data to anyone. The only thing that leaves your computer is what is needed to answer you.

## What is sent to the AI (Gemini, from Google, unless you change provider)

- **What you say, as text.** Your voice is turned into text on your own computer (Whisper); the audio is not sent anywhere.
- **The current conversation** (your latest questions and my answers), so we can keep talking about the same thing.
- **The name of the active window and its program**, to know what you are talking about.
- **Screenshots of your screen, only if you allow it** (`lina privacidad si`) and only when needed: in a game, if you talk about what you see, or if the AI asks for it.
  Never with **private mode** on, nor with **sensitive** windows (banks, billing, password managers…), nor while you haven't decided.
- **The result of the commands and tools** the AI uses to help you (for example, the list of installed programs or the text of a page you ask it to read).
- If you have set a **Tavily** key, the text of each web search, which is sent to Tavily. It may include what you ask or the name of a program or game you have open; Tavily does not receive your voice, screenshots or files.

## What is NOT sent

- Your voice recordings.
- Your keys and passwords (the system keyring keeps them; the AI can't read them and they are not printed in the log).
- Your files, unless you ask for something that requires reading one (then only what is read for that task).
- Screenshots in private mode, with sensitive windows or without your permission.

## What private mode does

Turn it on with «activa el modo privado»; only you can turn it off, with the shortcut, saying «quita el modo privado». The AI can turn it on but not off. It is remembered across restarts.

**While it is on:**

- No screenshot of your screen is taken or sent, and the AI can't ask for one.
- I don't answer «Oye Lina»: I only listen with the shortcut.
- What just happened is not kept (see below), and turning it on deletes whatever there was.
- I can't try KDE settings that need checking by looking at the panel.

**What does NOT change. It is not an incognito mode:**

- What you say is still sent to the AI as text, with the current conversation, the name of the active window and the result of the tools.
- Searches are still sent to Tavily or DuckDuckGo.
- What was already in the conversation stays there: turning it on doesn't delete it.
- Everything else is still saved: the log (including your questions, if `privacidad.registrar_preguntas` is on), the action log, the change journal, the recipes I learn, the timings and what you ask me to remember, and I keep using those memories.

## What Google says about what it receives

With the **free** key, according to Google's current terms, what is sent may be used to improve its products and may be reviewed by people; with a **paid** key it is not. Check the Gemini API terms before sending anything you don't want to share. If you work with confidential information, use the paid key, a provider that meets what your company requires, or private mode.

## What Lina stores on your computer

| What | Where | How to delete it |
|---|---|---|
| Change journal and copies for undoing | `~/.local/share/lina/diario` | `lina olvidar diario` |
| Action log (commands run) | `~/.local/state/lina/acciones.log` (rotates itself at ~1 MB) | `lina olvidar acciones` |
| What you ask me to remember («remember that…»; only you write it, with the hotkey, never the AI nor Lina on its own, and never passwords or keys; the AI only receives what is relevant to each request) | `~/.local/share/lina/memoria.json` | `lina memoria` (view and delete one), `lina olvidar memoria` |
| The websites you choose for each topic (`lina fuentes`; only you write them, never the AI, and for now they are only saved) | `~/.local/share/lina/fuentes.json` (only you can read it) | `lina fuentes quitar`, `lina olvidar fuentes` |
| Learned recipes (what you already asked me that went well: the phrase, the steps and how it was checked; never passwords) | `~/.local/share/lina/recetas.json` | `lina olvidar recetas` or `lina recetas borrar todas` |
| Timings of each request (numbers only, never what you say; `lina tiempos` summarises them) | `~/.local/state/lina/tiempos.jsonl` (trims itself at ~200 KB) | `lina olvidar tiempos` |
| How each shortcut listen ended (by silence, by your press…), with the day without the time and timings; never audio or text (`lina tiempos escucha`) | `~/.local/state/lina/escuchas.jsonl` (last 5000) | `lina olvidar tiempos` |
| Tokens and duration of each AI call, with the model, its reason (normal, retry…), the day without the time and a fingerprint of the fixed prefix (to know whether the cache is used); never what you ask or what it answers (`lina tiempos ia`) | `~/.local/state/lina/llamadas_ia.jsonl` (last 5000) | `lina olvidar tiempos` |
| System log (what you say and I answer, unless you turn it off) | `journalctl --user -u lina` | `lina olvidar registro` |

So that what you say and I answer doesn't stay in the log: `lina config poner privacidad.registrar_preguntas false`.
Temporary recordings and screenshots live in your session's runtime folder (memory) and disappear when you log out; each screenshot is also deleted as soon as the request ends. A screenshot is only taken if it can be used: never in private mode, without your permission or with a sensitive window; in a game, when you press the hotkey; outside a game, after you speak and only if what you say needs it, and only if the same window is still in front (on desktops that do not say which window is active, like GNOME on Wayland without xdotool, it is taken when you press, as before).

## How to decide

```
lina privacidad          explains it and asks you
lina privacidad si       I allow screenshots when needed
lina privacidad no       never screenshots
```

The AI can't change this decision on its own: you make it. If you left it on «preguntar» and, for what you ask, Lina needs to see your screen, she will ask you
(explaining that the screenshot goes to Google) and it only turns on if you confirm by pressing the shortcut; hands-free voice doesn't count. If you said «no», she
doesn't insist: only you change it, in a terminal.

What just happened (your phrase, the tools used with their result and the answer of the last 4 requests) is kept in memory only for 15 minutes, to answer you if you ask what occurred, and it is then sent to the AI. In **private mode** none of this is kept, and turning it on deletes whatever there was.
