# MINA — Installation Guide

**Reference version:** v2.15.4
**Project status:** Final Integrated and Validated Prototype (educational/research)
**Verification status:** Instructions prepared from static inspection of `MINA_CODE_AUDIT.zip`; **a fresh installation has not yet been executed or verified**.

## 1. Prerequisites

- macOS (the development environment described by the project documentation). Other operating systems have not been verified for this release.
- Python 3 and `python3`, `pip`, and `venv` available in Terminal. **The exact Python version compatibility range is not established by the audit.**
- Network access for package installation and optional API-backed features.
- An OpenAI API key **only** when using features that call OpenAI. Such calls may incur charges.
- Optional: Google Cloud OAuth Desktop client credentials for Google Calendar integration.

The repository is intended to contain **source code**, not the developer's `.venv` directory, private `.env` file, Google tokens, or personal local data.

## 2. Obtain the source

After publication, clone your actual GitHub repository (replace the placeholder):

```bash
git clone https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY>.git
cd <YOUR_REPOSITORY>
```

For a local pre-publication checkout, instead open the prepared `MINA_GitHub` directory:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_GitHub
```

**Check before installing:** `streamlit_app.py`, `requirements.txt`, `requirements_ui.txt`, `requirements_calendar_v2_7.txt`, the referenced `mina_*.py` modules, and the theme CSS files must be present. The GitHub package is **not yet certified complete**; the audit ZIP intentionally omitted user data and some example/evaluation resources.

## 3. Create an isolated Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Avoid copying `.venv` from the original 1.62-GB working directory: it contains locally installed packages and may not be portable.

## 4. Install dependencies

The audited codebase distributes dependencies across three files:

```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements_ui.txt
python -m pip install -r requirements_calendar_v2_7.txt
```

- `requirements.txt`: `openai`, `python-dotenv`, `sentence-transformers`, `pytest`.
- `requirements_ui.txt`: `streamlit>=1.52,<2`; the app uses `st.chat_input(accept_audio=True)`.
- `requirements_calendar_v2_7.txt`: Google Calendar API client and OAuth libraries.

Google Calendar dependencies may be omitted when that feature is unused, but the full dependency installation is the safer starting point for reproducing the integrated prototype. **The three files have not yet been tested together in a fresh environment.** `sentence-transformers` and its dependencies may use significant disk space and may download model assets for relevant features.

## 5. Configure OpenAI access (optional for offline-only workflows)

Create a **private** `.env` file in the repository root when OpenAI-backed features are needed. For example:

```bash
printf 'OPENAI_API_KEY=replace_with_your_private_key\n' > .env
chmod 600 .env
```

Replace the placeholder on your own computer. **Never share or commit `.env`, API keys, or screenshots of them.** The audit archive did not include `.env.example`, so this guide does not assume it exists; a sanitized template should be created and reviewed as part of final repository packaging.

Without an API key, some local features may still work, but LLM, transcription, or speech output requests can fail or be unavailable.

## 6. Configure Google Calendar (optional)

The code in `mina_google_calendar.py` expects:

- `local_data/google_oauth_client.json` — a user-supplied Google OAuth **Desktop** client file.
- `local_data/google_calendar_token.json` — generated locally by the OAuth flow.

Do not distribute either file. Create the directory if necessary:

```bash
mkdir -p local_data
```

Enable the Google Calendar API and configure the OAuth consent screen/desktop client for your own Google Cloud project before using the app's connection workflow. Google Calendar access and live authentication were **not** exercised by this installation audit. The code requests the `https://www.googleapis.com/auth/calendar.events` scope.

## 7. Start MINA

From the repository root, with the virtual environment active:

```bash
python -m streamlit run streamlit_app.py
```

Open the local URL printed by Streamlit in your browser. Stop the server with `Control + C` in Terminal.

The entry point above is documented in the actual `streamlit_app.py` header and v2.15.4 update notes. The displayed Welcome Page depends on repository CSS files, so do not omit those assets.

## 8. First-run behavior, privacy, and limits

- Some workflows require user-provided family information, saved places, or calendar credentials; the application should not invent missing addresses, opening hours, or school schedules.
- Public geocoding requires opt-in. When enabled and invoked, address/coordinate data may be sent to third-party mapping services; consult the in-app consent wording before enabling it.
- Optional conversation memory and reminders use local data under `~/.mina/` in some v2.15 workflows. Conversation memory is **not encrypted at rest** in this prototype.
- Local reminders do **not** deliver background push notifications when MINA is closed.
- Public API access and live route results depend on external service availability.

## 9. Initial checks

With the virtual environment active:

```bash
python -m compileall -q .
python -m unittest -q test_mina_welcome_tagline_v2154.py
```

`compileall` only checks compilation; it is **not** an end-to-end test. The tagline test checks a narrow v2.15.4 UI change. Run broader regression tests and manually verify relevant workflows before claiming a reproducible release; document outcomes in `docs/TESTS.md` and `docs/RESULTS.md`.

## 10. Troubleshooting

| Symptom | First check |
|---|---|
| `ModuleNotFoundError: streamlit` | Activate `.venv`, then install `requirements_ui.txt`. |
| Missing other third-party packages | Install all three requirements files in the same active environment. |
| OpenAI authentication error | Check whether `.env` exists locally and contains a valid private key. |
| Calendar not connected | Check OAuth Desktop client setup and local file `local_data/google_oauth_client.json`. |
| Missing theme / Welcome Page error | Confirm the `mina_theme_*.css` files and `mina_welcome_polish_v2151.css` are present. |
| Missing saved places / example data | Provide safe local configuration. The audit ZIP excluded private data and may not include every example/evaluation artifact. |

## Release verification still required

Before publishing instructions as *verified*, perform a clean checkout, install the requirements into a new virtual environment, launch Streamlit, test the main UI and configured integrations, review all committed files for personal information/secrets, and record exact tested Python/platform versions. Until then, this guide is **installation instructions, not a clean-install certification**.
