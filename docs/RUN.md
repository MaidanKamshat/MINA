# Running MINA

**Reference:** MINA v2.15.4 — Final Integrated and Validated Prototype
**Documentation status:** Based on inspection of the supplied source archive; **not yet verified by a clean installation and full end-to-end run**.

## 1. Before you start

Follow [Installation](INSTALLATION.md) to create a Python virtual environment and install the required packages. The app's entry point is `streamlit_app.py`, in the repository root. Run all commands below from that root (the directory containing `streamlit_app.py`).

For the local preparation folder on the original developer Mac:

```bash
cd ~/Desktop/CMU/labs/capstone/MINA_GitHub
source .venv/bin/activate
```

If `.venv` does not yet exist in this separate GitHub preparation directory, first complete the installation steps; **do not** activate or copy the original project's `.venv` as a substitute for clean-install testing.

## 2. Launch the application

```bash
python -m streamlit run streamlit_app.py
```

Streamlit prints a **Local URL** (typically `http://localhost:8501`). Open the URL displayed in your own terminal; do not assume the port is always 8501. Keep Terminal running while using MINA.

To stop the application, focus the Terminal process and press **Control + C**. This stops the Streamlit server; it does not remove files or uninstall MINA.

If a previous Streamlit server is still active, stop that server first or use the actual URL of the newly launched instance.

## 3. First-time orientation

The source code provides a welcome page with **Get started**, **Explore MINA**, **How it works**, and **Features**. The v2.15.4 welcome tagline reads:

> Plan your day, capture tasks, and make room for what truly matters.

The application also provides **Settings & Family Hub**, where configuration and family-specific functions can be managed. UI names can vary slightly by state, so use the labels in the running app as authoritative.

### Interaction modes

In Settings, the source defines these modes:

- **Auto (recommended)**
- **Assistant**
- **Directions**
- **Family planner**

A chat composer accepts typed input, and supported Streamlit versions provide microphone input through `st.chat_input(accept_audio=True)`. Voice transcription and spoken responses can require an OpenAI API key and external connectivity. Speech output may incur API charges.

## 4. Suggested walkthrough (non-destructive first)

These are **manual inspection steps**, not a claim that they have been successfully executed against this release package.

1. Launch MINA and inspect the welcome page, tagline, navigation controls, and theme.
2. Select **Get started**, and confirm that the chat interface appears.
3. Open **Settings & Family Hub**; inspect the available settings and return to the main view.
4. Try a read-only or local workflow (e.g., inspect shopping lists or the local calendar) using **fictional demo values**, where available.
5. Review the calendar **create-preview / confirm / cancel** interface without approving any real Google Calendar event.
6. Check the route-planning settings. Do **not** enable public geocoding or live routing for a personal address solely for a demonstration.
7. If you enable optional conversation memory, understand that local saved text is not encrypted at rest. Use fictional content for demonstrations.
8. Close the running server with **Control + C**.

**Note about demo data:** Source references `examples/demo_saved_places_v1_8.json` and `examples/demo_today_tasks_v2_2.json`. The `MINA_CODE_AUDIT.zip` used for repository preparation omitted the `examples/` contents. Demo workflows relying on these files may not work until **sanitized, approved** demo files are restored in the public package. Do not substitute your private `local_data/` files.

## 5. Optional integrations

### OpenAI-backed capabilities

Configure `OPENAI_API_KEY` privately as described in [Installation](INSTALLATION.md). Local or offline-oriented functions may be available without it, but LLM responses, transcription, or speech synthesis may require access.

### Google Calendar

The application's settings include **Connect / reconnect Google Calendar**, **Refresh Google events**, and a setting to save *confirmed* events to Google when connected. The source expects locally supplied OAuth credentials at `local_data/google_oauth_client.json` and a local token file after authorization. Neither should be committed to GitHub.

Google Calendar writes require OAuth and explicit per-action approval. When demonstrating, prefer cancellation or local-only handling to avoid creating unwanted real events.

### Saved Places, routes, and public geocoding

Route planning can depend on user-supplied Saved Places, verified pins, dates, opening hours, and pickup constraints. The source has a separate setting for consenting to public geocoding and HeiGIT routing for saved addresses. Do not imply that MINA knows the user's address automatically or that unverified travel times and hours are authoritative.

### Reminders and conversation memory

Standalone reminders are separate from Google Calendar. They do **not** send background push notifications when MINA is closed. Persistent conversation memory is opt-in and stores local text; it is not encrypted at rest in this prototype.

## 6. Safety boundaries

- Preview and explicitly confirm supported local edits and Calendar actions. Do not treat the assistant's proposed text as an executed action.
- External email sending and external shopping-list writes remain disabled in this version.
- Do not copy `.env`, Google credentials, tokens, or private `local_data/` into a public repository.
- Test route and location features using public or fictional demonstration information rather than personal addresses.

## 7. Minimal technical checks

From the repository root, with dependencies installed:

```bash
python -m compileall -q .
python -m unittest -q test_mina_welcome_tagline_v2154.py
```

These checks do **not** establish operational correctness of the calendar, routing, voice, or external APIs. For verified regression coverage and manually witnessed scenarios, see [Tests](TESTS.md) and [Results](RESULTS.md) when those documents have been completed.

## 8. Troubleshooting

| Issue | First action |
|---|---|
| `No module named streamlit` | Activate the right `.venv` and install `requirements_ui.txt`. |
| Another app opens at `localhost:8501` | Check which server is running and use the Local URL shown by the new Streamlit process. |
| Missing CSS / welcome screen error | Ensure `mina_theme_v2_1.css`, `mina_theme_v2_2.css`, `mina_theme_v2_8.css`, and `mina_welcome_polish_v2151.css` are beside `streamlit_app.py`. |
| Example/demo file error | Restore only the approved sanitized demo files under `examples/`. |
| Google Calendar is unavailable | Confirm the optional OAuth client is correctly configured locally and that the API is enabled. |
| Live AI, voice, or maps fail | Check network access, permissions/consent, configuration, and the relevant external service; do not assume a missing response is a valid plan. |

## 9. Verification record

- **Source inspection:** `streamlit_app.py` launch instructions, interface labels, CSS paths, and module imports checked against the supplied archive.
- **Fresh checkout / environment creation / runtime launch:** **Pending**.
- **Integration and manual regression tests of this public-package layout:** **Pending**.
- **Previously reported user acceptance tests on the original development setup:** Document separately with their precise scope and evidence; do not present them as clean-install verification of this package.
