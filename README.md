# Hangar

A file library backed by Telegram's free storage, with two separate sides:

- **`/`** — the **public library**. Anyone can browse by shelf, search, and
  download. No account, no login.
- **`/admin`** — your **private dashboard**. Password-protected. Upload
  files, sort them onto shelves (e.g. "Psychology", "Self-Help", "Notes"),
  rename or remove them.

Visitors can only ever read and download — there's no public upload, so you
stay in control of what's on the shelves.

**How it's free:** Telegram lets a bot send files into a chat or channel at
no cost and keeps them indefinitely. Hangar uses that as the storage layer —
your files live on Telegram's servers — and just keeps a small local index
(filename, size, date, a share link) in a `hangar.db` file next to the app.
Downloading, whether by you or by someone with a share link, streams the
file live from Telegram through Hangar, so nobody needs a Telegram account
to receive it.

**Be aware of the one real limit:** Telegram's Bot API caps a single
*upload* at 50MB. That's a Telegram rule, not something in this code —
there's no free way around it while using the standard Bot API.

## Setup (10 minutes)

### 1. Create your bot
Message **@BotFather** on Telegram → `/newbot` → follow the prompts → copy
the token it gives you (looks like `123456:ABC-DEF...`).

### 2. Decide where files get stored
Pick one:
- **Simplest:** message your new bot anything once (so it knows who you
  are), then message **@userinfobot** to get your own numeric Telegram user
  ID. Use that as `STORAGE_CHAT_ID`.
- **More headroom / organized:** create a private Telegram channel, add
  your bot as an admin, then use the channel's ID (looks like `-100...`;
  forward a message from the channel to @userinfobot to find it).

### 3. Install and configure
```bash
pip install -r requirements.txt
cp .env.example .env
```
Edit `.env`:
```
BOT_TOKEN=123456:ABC-DEF...
STORAGE_CHAT_ID=your_id_here
APP_PASSWORD=pick-something-only-you-know
SECRET_KEY=any-long-random-string
```

### 4. Run it locally
```bash
export $(cat .env | xargs)   # or use python-dotenv / your host's env settings
python app.py
```
- Public library: `http://localhost:5000/`
- Your dashboard: `http://localhost:5000/admin` — sign in with `APP_PASSWORD`

## Getting a real public link (so share links work for other people)

Locally, `/share/<token>` links only work on your own machine. To actually
hand a link to someone else, Hangar needs to live somewhere with a public
URL. Two free ways to do that:

**Option A — deploy for free (recommended, stays on 24/7)**
Render, Railway, and Fly.io all have free tiers that run a Flask app like
this out of the box:
1. Push this folder to a GitHub repo.
2. On Render: New → Web Service → connect the repo → build command
   `pip install -r requirements.txt` → start command
   `gunicorn app:app` → add the same environment variables from `.env`.
3. Render gives you a URL like `https://yourname.onrender.com` — that's
   your permanent Hangar, and share links look like
   `https://yourname.onrender.com/share/xyz...`.

**Option B — quick temporary link from your own machine**
Useful for testing, not for something you rely on long-term:
```bash
python app.py
# in another terminal:
npx localtunnel --port 5000
```
This prints a temporary public URL that forwards to your local app.

## Using it

### Your dashboard (`/admin`)
- **Upload:** drag a file onto the dock, or click it to browse.
- **Shelve under:** type a category (e.g. "Psychology", "Self-Help",
  "Notes") into the field below the dock before uploading — it becomes a
  shelf visitors can browse by on the public side. It's just a label, not a
  real folder, and autocompletes from shelves you've already used.
- **Manifest:** every file shows its type, size, and when it was logged.
- **Get / Share:** download it yourself, or copy a direct link to hand to
  one specific person.
- **Rename / Delete:** delete also removes the underlying message from your
  Telegram storage chat, freeing it from the index.
- **View public library ↗:** opens the public side in a new tab so you can
  see what visitors see.

### The public library (`/`)
- No login. Visitors pick a shelf on the left, or search across everything.
- Each item shows its shelf, size, and a Download button — that's the only
  action they have. They can't upload, rename, or delete anything.
- Share this root URL (e.g. `https://yourname.onrender.com`) with anyone —
  that's the whole library, ready to browse.

## Files in this project
```
app.py              Flask backend — auth, upload, download, share routes
templates/           HTML pages (login, dashboard, public share page)
static/style.css     Design
static/app.js        Dashboard behavior (upload, list, search, actions)
requirements.txt     Dependencies
.env.example         Copy to .env and fill in
```
