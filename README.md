# Poll & Group Decision Maker

A Telegram Mini App that helps friends and group chats settle things: where to eat, what to watch, who pays. Create a poll, send it to the chat, vote, and let a shared spin wheel handle ties.

The main learning goal is **deep links**: every poll is shared with a `startapp` link that opens the right screen inside Telegram.

## Features

**Three ways to vote**

- **Pick one:** everyone chooses a single option.
- **Rank them:** ranked-choice voting. You can step through the count round by round.
- **Swipe cards:** visual flashcards. Swipe right for yes, left for no.

**Spin wheel**

- **Just spin:** a wheel with no voting, for quick decisions.
- **Shared result:** the server picks the outcome, so everyone in the chat sees the same spin.
- **Tie-breaker:** a tied poll offers a spin between only the tied options.
- **Weighted spin:** slice sizes follow the vote counts.
- **Elimination:** each result is removed until one option is left, which suits "who pays".
- **Replay:** a wheel link lets latecomers watch the last spin.

**Group features**

- Results stay hidden until you vote, so early votes don't sway anyone.
- Results and spins update live while the screen is open.
- Opening the app from a group shows that chat's decisions, using `chat_instance`.
- The creator can make a result final, close voting, or reopen.
- Optional settings: let anyone add options, hide who voted, close automatically.
- Each option keeps one colour everywhere, and the app follows the user's Telegram theme.
- Quick-start templates: Lunch, Movie night, Weekend plan, Who pays.

## How the deep links work

| Link | Opens |
| --- | --- |
| `https://t.me/<bot>/<app>?startapp=v_<id>` | The ballot (or results if you already voted) |
| `https://t.me/<bot>/<app>?startapp=r_<id>` | The results |
| `https://t.me/<bot>/<app>?startapp=s_<id>` | The wheel, showing the last spin |

1. The `startapp` value reaches the app as `initDataUnsafe.start_param` and the URL parameter `tgWebAppStartParam`.
2. `screenFromStartParam()` in `static/js/app.js` turns it into a screen.
3. The value only chooses a screen. Who the user is always comes from the signed `initData`, which `app/auth.py` checks on every request.

Sharing has three routes, so you can compare them:

| Route | Where in the code | Result |
| --- | --- | --- |
| `shareMessage` (Bot API 8.0+) | `shareRich()` in `tg.js`, `prepared_message()` in `api.py` | A rich message with an open button |
| `t.me/share/url` | `shareLink()` in `tg.js` | A plain link, used as the fallback |
| Inline mode | `_handle_inline_query()` in `bot.py` | Type `@yourbot` in any chat and pick a poll |

Group buttons use a `t.me` URL instead of a `web_app` button, because `web_app` buttons aren't available in groups.

## Run it in a browser (no Telegram needed)

You need Python 3.10 or newer.

```bash
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
python -m pytest
python -m flask --app wsgi run
```

Open http://127.0.0.1:5000/?as=Dara, then open http://127.0.0.1:5000/?as=Sok in a private window to be a second person. The Share screen gives you test links.

| Add to the address | What it does |
| --- | --- |
| `?as=Name` | Sets the fake user |
| `&startapp=v_<id>` | Simulates a deep link |
| `&chat=abc` | Simulates opening from a group chat |

## Connect it to Telegram

1. **Create the bot.** In [@BotFather](https://t.me/BotFather), send `/newbot` and copy the token.
2. **Get a public HTTPS address.** Telegram won't load a plain `http://` page. For testing, use a tunnel such as `cloudflared tunnel --url http://127.0.0.1:5000`.
3. **Create the Mini App.** Send `/newapp` to BotFather, pick your bot, and give it your HTTPS address. The short name you choose becomes the end of the link.
4. **Turn on inline mode.** Send `/setinline` to BotFather. Inline sharing and `shareMessage` both use it.
5. **Fill in `.env`.** Set every value and change `DEV_MODE` to `0`.
6. **Connect the webhook.** Restart the server, then run `python scripts/set_webhook.py`.
7. **Try it.** Open `https://t.me/<bot>/<app>`, create a poll, and send it to a group.

> **Keep `DEV_MODE=0` on anything public, including a tunnel.** With it on, anyone can sign in as anyone. The app logs a warning at startup when it's on.

To deploy, run `gunicorn wsgi:app` on any Python host. SQLite needs a persistent disk, or your polls vanish on every redeploy.

## Project layout

```
app/
  api.py        JSON API: polls, votes, spins, results
  auth.py       initData signature check
  bot.py        Webhook: /start, /new, inline mode
  voting.py     Vote counting (no Flask, easy to test)
  telegram.py   Bot API calls and deep-link building
  db.py         SQLite schema
  config.py     Settings from .env
static/
  index.html    Page shell
  css/app.css   Styles, based on Telegram theme variables
  js/app.js     Screens and routing
  js/wheel.js   Canvas spin wheel
  js/tg.js      Telegram.WebApp wrapper with browser fallbacks
  js/api.js     API client
  js/ui.js      DOM helper and option colours
scripts/set_webhook.py
tests/          71 tests
wsgi.py         Entry point
```

## How decisions are made

**Ranked choice.** Each ballot counts for its highest-ranked option still in the race. Over half the active ballots wins. Otherwise last place drops out and those ballots move to their next choice. A tie for last place is settled by overall ranking score. If that's also level, those options go out together, unless they're all that's left, which is a tie.

**Spins.** The server draws the result with Python's `secrets` module and stores it. A second spin within 6 seconds returns the running spin, so a double tap can't re-roll. A spin only becomes final when the creator confirms it.

## Known limits

- Live updates check the server every 3 seconds, so they aren't instant.
- There is no rate limiting yet. Add it before opening this to the public.
- A login expires after 24 hours, so someone who leaves the app open that long must reopen it.
- SQLite suits one server. Move to PostgreSQL if you ever run several.

## Ideas for later

- A bot message in the group when voting closes or a spin lands
- Scheduled reminders for people who haven't voted
- Recurring polls, such as a weekly lunch vote
- Result cards as images, using `shareToStory`
- Location-based restaurant options



Option A: GitHub (recommended)
You set this up once. After that, each update takes about 30 seconds.

Setup (one time)
1. On your PC, turn this folder into its own Git repository and push it to GitHub. First, create an empty repository on github.com, for example poll-group-decision-maker. Then run:


cd /d/Beltie-IU/MyProject/miniapp/poll-group-decision-maker
git init
git add .
git commit -m "First version"
git branch -M main
git remote add origin https://github.com/Sreyroth-Nok/poll-group-decision-maker.git
git push -u origin main
Your .gitignore already leaves out .env, .venv and data.sqlite3, so your token and database never go to GitHub. To be sure, run git status before committing and check that .env isn't in the list.

2. On PythonAnywhere (Bash console), swap the uploaded folder for a copy from GitHub. Your .env and database are kept:


cd ~
mv poll-app poll-app-old
git clone https://github.com/Sreyroth-Nok/poll-group-decision-maker.git poll-app
cp poll-app-old/.env poll-app/
cp poll-app-old/data.sqlite3 poll-app/ 2>/dev/null
Click Reload on the Web tab and check that the app still works. Once it does, you can delete the old folder with rm -r ~/poll-app-old.

If your GitHub repository is private, git clone will ask for a password. Use a GitHub personal access token there, not your account password. You can create one at GitHub → Settings → Developer settings → Personal access tokens.

Every time you update
On your PC:


git add .
git commit -m "Describe what you changed"
git push
On PythonAnywhere (Bash console):


cd ~/poll-app
git pull
Then click Reload on the Web tab.

Some changes need one extra step:

If you changed…	Also run
requirements.txt	workon pollenv && pip install -r requirements.txt
The bot commands in set_webhook.py	workon pollenv && python scripts/set_webhook.py
Only HTML, CSS or JS	Nothing extra, but Telegram may cache old files. Close the Mini App fully and open it again.
Option B: Upload files by hand (no GitHub)
In the Files tab, go to /home/Zzzroth/poll-app/, open the folder you changed (for example static/js), and upload the new file. It replaces the old one.
Click Reload on the Web tab.
This works for one or two files, but it's easy to forget one. Never upload your PC's .env or data.sqlite3 this way, because that would overwrite the server's copies.