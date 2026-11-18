# Privacy: what leaves your computer and what doesn't

Lina has no telemetry: she sends no statistics or usage data to anyone. The only thing that leaves your computer is what is needed to answer you.

## What is sent to the AI (Gemini, from Google, unless you change provider)

- **What you say, as text.** Your voice is turned into text on your own computer (Whisper); the audio is not sent anywhere.
- **The current conversation** (your latest questions and my answers), so we can keep talking about the same thing.
- **The name of the active window and its program**, to know what you are talking about.
- **Screenshots of your screen, only if you allow it** (`lina privacidad si`) and only when needed: in a game, if you talk about what you see, or if the AI asks for it.
  Never with **private mode** on, nor with **sensitive** windows (banks, billing, password managers…), nor while you haven't decided.
- **What you have copied or selected, only when your sentence is about it** («summarise this», «translate what I copied»): up to 4000 characters.
  Never in **private mode**, nor by **hands-free** (only with the shortcut or `lina di`), nor with a **sensitive** window in front, nor if your password manager
  marks it as a **password** (KeePassXC does). The log only records what was looked at and how many characters.
- **The result of the commands and tools** the AI uses to help you (for example, the list of installed programs or the text of a page you ask it to read).
- If you have set a **Tavily** key, the text of each web search, which is sent to Tavily. It may include what you ask or the name of a program or game you have open; Tavily does not receive your voice, screenshots or files.

## Where each web search goes (`ia.busqueda`)

With `auto`, the default, Lina tries in this order and keeps the first thing that gives results. In every case only **the search text** leaves: never your voice, screenshots or files.

1. **Google, inside Gemini**, if you have a paid key with room left in your cap (or a Gemini key that can search: in our tests, the free one could not). It is a separate query to Google, which already receives your questions. With the paid key, after the month's free searches, it costs money and counts towards your cap.
2. **Tavily**, if you have a key.
3. **DuckDuckGo**, only if you turn it on (`lina config poner ia.busqueda_reserva true`). It is off by default because it is unreliable: it often takes programs for robots and then returns nothing. DuckDuckGo sees the search text and your IP address. Lina does not pretend to be a browser to get around its block. The first time it is used, Lina tells you.
4. **Wikipedia and some game wikis** (Fandom, minecraft.wiki, wiki.gg, bg3.wiki, WikiDex), with their own search, no key. They see the search text and your IP address. They are only used for encyclopedic questions (not prices, news, the weather or results). Lina also asks their API for the extract of the first page found, whose text reaches the AI. The first time they are used, you get a notification.

**Whether a game works on Linux.** When you ask whether a Steam game works on Linux or needs Proton, Lina checks the Steam store page and the ProtonDB summary, with any `ia.busqueda`. Both only see the game's Steam number and your IP address; if the game is not in your library, the Steam store search also sees its name. The first time you get a notification.

With `tavily` only Tavily is used (and DuckDuckGo if you turn it on); with `google`, only Gemini's (and DuckDuckGo if you turn it on); with `ninguna`, nothing: your question doesn't go to any search engine. It only searches, like `auto` and for that request only, if you ask for it in your own words («búscalo igualmente», «mira en internet…») or if you say yes when Lina offers to search just this once (that «sí», with the shortcut). The AI can't decide it for you: that you are asking is checked by a separate query that only sees your words. Like everything you say, those words do go to the AI provider.

- If you save **sources** (a website for a topic) and use Gemini, the following:
  - **To Gemini:** the list of your topics in each request that may use them and, when the AI picks one, one more query with only that topic and your question. That query goes through your paid key if you have one and your spending cap has room left; otherwise, through the free key. What the website returns also reaches the AI.
  - **To Tavily or DuckDuckGo:** the search text and your source's domain, to search only there. DuckDuckGo is only used if you turned it on (`busqueda_reserva`) and Tavily does not answer or there is no key.
  - **With `ia.busqueda` set to `auto` or `tavily` without a Tavily key and `busqueda_reserva` on:** your query goes to DuckDuckGo, limited to that website. If it finds nothing, the saved page is downloaded, as in the next case.
  - **With `ia.busqueda` set to `ninguna` or `google`, or without a Tavily key and with `busqueda_reserva` off (the default):** no search engine is used for your source. Your computer downloads the saved page directly, so **that website sees your IP address**, and its text is sent to the AI.

## What is NOT sent

- Your voice recordings.
- Your keys and passwords (the system keyring keeps them; the AI can't read them and they are not printed in the log).
- Your files, unless you ask for something that requires reading one (then only what is read for that task).
- Screenshots in private mode, with sensitive windows or without your permission.
- What you have copied or selected in private mode, by hands-free, with a sensitive window in front or if your password manager marks it as a password.

## What private mode does

Turn it on with «activa el modo privado»; only you can turn it off, with the shortcut, saying «quita el modo privado». The AI can turn it on but not off. It is remembered across restarts.

**While it is on:**

- No screenshot of your screen is taken or sent, and the AI can't ask for one.
- The AI can't look at what you have copied or selected.
- I don't answer «Oye Lina»: I only listen with the shortcut.
- What just happened is not kept (see below), and turning it on deletes whatever there was.
- I can't try KDE settings that need checking by looking at the panel.
- The log doesn't keep what you say or what I answer, not even in what the service writes to the system log (`journalctl --user -u lina`), even if `privacidad.registrar_preguntas` is on. Only the start of each line is left («Pregunta: …», «Respuesta [voz]: …»). What was already in the journal before is not deleted.
- I don't learn new recipes. I keep using the ones I already have.
- I don't note anything new in my memory: if you say «recuerda que…», I tell you I'm not noting it. I keep using what I already had, and «olvida lo de…» works.

**What private mode does NOT cover. It is not an incognito mode:**

- **The AI provider still receives your questions**: what you say is sent to it as text, with the current conversation, the name of the active window and the result of the tools. What it does with that is up to its terms (see below).
- **Steam and ProtonDB see your IP address** when you ask whether a game works on Linux (and the game's number; the Steam store search also sees its name if it isn't in your library).
- Searches are still sent wherever they go (Google inside Gemini, Tavily, DuckDuckGo if you turned it on, Wikipedia and the game wikis), and the web pages I read see your IP address.
- What was already in the conversation stays there: turning it on doesn't delete it.
- Everything else is still saved: the action log (the commands that run), the change journal for undoing, and the timings (numbers only).

## What Google says about what it receives

With the **free** key, according to Google's current terms, what is sent may be used to improve its products and may be reviewed by people; with a **paid** key it is not. Check the Gemini API terms before sending anything you don't want to share. If you work with confidential information, use the paid key, a provider that meets what your company requires, or private mode.

## What Lina stores on your computer

| What | Where | How to delete it |
|---|---|---|
| Change journal and copies for undoing | `~/.local/share/lina/diario` | `lina olvidar diario` |
| Action log (commands run) | `~/.local/state/lina/acciones.log` (rotates itself at ~1 MB) | `lina olvidar acciones` |
| What you ask me to remember («remember that…»; only you write it, with the hotkey, never the AI nor Lina on its own, and never passwords or keys; the AI only receives what is relevant to each request) | `~/.local/share/lina/memoria.json` | `lina memoria` (view and delete one), `lina olvidar memoria` |
| The websites you choose for each topic (`lina fuentes`; only you write them, never the AI; they are used when answering, as explained above) | `~/.local/share/lina/fuentes.json` (only you can read it) | `lina fuentes quitar`, `lina olvidar fuentes` |
| Learned recipes (what you already asked me that went well: the phrase, the steps and how it was checked; never passwords) | `~/.local/share/lina/recetas.json` | `lina olvidar recetas` or `lina recetas borrar todas` |
| Timings of each request (numbers only and how it arrived: shortcut, hands-free or `lina di`; never what you say; `lina tiempos` summarises the last 14 days; test runs such as `lina probar-ia` are not stored) | `~/.local/state/lina/tiempos.jsonl` (trims itself at ~200 KB) | `lina olvidar tiempos` |
| How each shortcut listen ended (by silence, by your press…), with the day without the time and timings; never audio or text (`lina tiempos escucha`) | `~/.local/state/lina/escuchas.jsonl` (last 5000) | `lina olvidar tiempos` |
| Tokens and duration of each AI call, with the model, its reason (normal, retry…), the day without the time and a fingerprint of the fixed prefix (to know whether the cache is used); never what you ask or what it answers (`lina tiempos ia`) | `~/.local/state/lina/llamadas_ia.jsonl` (last 5000) | `lina olvidar tiempos` |
| How each check that a question belongs to a source's topic ended: real use or `lina fuentes probar`, fits or not, attempts, seconds, the day without the time and whether it used the paid key; never the topic or the question (`lina tiempos ia`) | `~/.local/state/lina/comprobaciones_fuente.jsonl` | `lina olvidar tiempos` |
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
