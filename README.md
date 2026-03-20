# MouseTrainer

MouseTrainer is a Windows-focused behavioral training application for mouse experiments. The repository contains:

- A Python desktop/controller app that runs the training session, talks to the Arduino, logs behavioral data, optionally triggers imaging, and saves session output.
- Arduino firmware for the behavioral controller hardware.
- Runtime configuration files, local data/log directories, and build scripts for packaging the app as a standalone `.exe`.

Project workflow preference note:
- [PROJECT_AUTOMATION_PREFS.md](C:/Users/Max/Documents/Classes/Gonzales%20Lab/Behavioral/mousetrainer/PROJECT_AUTOMATION_PREFS.md) documents the user's preference for how networked build/deploy actions should be handled in this repo.

If this repository will be made public, review the `config/` folder before publishing. Files such as `credentials.json` and `.env` can contain secrets or internal IDs and should be replaced with sanitized examples if needed.

## Repository layout

```text
mousetrainer/
|-- src/mousetrainer/               Python application package
|   |-- behavioral_master.py        Main session controller and orchestration logic
|   |-- TCPClient.py                TCP client for Prairie/imaging integration
|   |-- cursor_utils.py             Pygame visual cursor/BCI display
|   |-- paths.py                    Runtime path resolution for source vs bundled app
|   |-- __main__.py                 Package entry point
|   `-- __init__.py
|-- firmware/behavioral_controller/ Arduino sketch and supporting C++ classes
|-- config/                         Runtime configuration and credentials
|-- data/                           Local output data written during/after sessions
|   |-- raw/                        Raw capture JSON files
|   `-- sessions/                   Local fallback session saves
|-- logs/                           Runtime error logs
|-- tools/                          Helper scripts for development and analysis
|-- launcher.py                     Thin launcher used by PyInstaller
|-- run.bat                         Development startup wrapper
|-- build.ps1                       Windows build script for standalone executable
|-- mousetrainer.spec               PyInstaller spec file
|-- requirements.txt                Python dependencies
|-- webapp/                         Separately deployable Vercel-hosted status site
|-- worker/                         Legacy Cloudflare proxy (no longer required)
|-- pyproject.toml                  Python package metadata
`-- BUILD.md                        Short build/shipping notes
```

## Remote session website

The repository supports a split deployment model:

- `MouseTrainer.exe` can publish live session status in the background using `CLIENT_ID`.
- The browser UI and remote status API live under `webapp/` and can be updated independently from the packaged client.
- Client publishing settings live separately from web app display settings.

### Client-side status publishing

- `src/mousetrainer/remote_status.py` handles background HTTP publishing so session I/O is not blocked on website updates.
- `src/mousetrainer/client_status_config.py` loads the client publishing configuration.
- `config/remote_status.example.json` shows the optional runtime settings for the client publisher.

If remote publishing is disabled or unreachable, the session continues normally and terminal output remains unchanged.

### Web app deployment

- `webapp/config/clients.json` controls which client tabs are shown.
- `webapp/config/ui.json` controls the site title, subtitle, and refresh cadence.
- `webapp/public/` contains the static frontend assets served by Vercel.
- `webapp/app.py` serves the API routes and the root page for local testing, and is the entry point Vercel uses when `webapp/` is the project root.
- `webapp/status_store.py` uses Redis through Vercel Marketplace credentials in production and falls back to in-memory storage locally.
- `webapp/deploy.ps1` prepares the hosted app separately from `build.ps1`.
- `webapp/VERCEL.md` contains the Vercel CLI flow plus the dashboard steps for Redis, environment variables, and domains.

Example host start command:

```powershell
.\webapp\.venv\Scripts\python.exe -m uvicorn app:app --app-dir .\webapp --host 127.0.0.1 --port 8000
```

## How the code is organized

### 1. Python application

The main application code lives in `src/mousetrainer/`.

- `behavioral_master.py` is the core of the project. It:
  - prompts for animal ID, phase, flushing, and imaging options
  - connects to the Arduino over serial
  - sends session and trial configuration to the firmware
  - runs the main session loop
  - records behavioral events, encoder values, and optional imaging timestamps
  - saves data to Google Sheets and/or local JSON files
  - sends summary emails and logs runtime errors
- `cursor_utils.py` creates the Pygame-based cursor/target display used in wheel-based phases.
- `TCPClient.py` manages the TCP connection to the imaging server (`PrairieClient`).
- `paths.py` makes the app work both from source and from a versioned bundled release by resolving runtime `config/`, `firmware/`, `logs/`, and `data/` paths separately from the active code bundle.
- `startup_update.py` is the bootstrapper-side updater. It can sync approved config files, install a newer versioned client bundle, and optionally self-update the launcher.
- `startup_splash.py` shows a Windows splash screen with startup/update status before the console opens in the packaged app.
- `console_entry.py` is the console-mode worker that runs inside the active client bundle after the launcher finishes startup checks.
- `__main__.py` runs the package with `python -m mousetrainer`.

### 2. Firmware

The firmware is in `firmware/behavioral_controller/`.

- `behavioral_controller.ino` is the top-level Arduino sketch.
- The supporting `.h` and `.cpp` files break out hardware-specific logic such as wheel tracking, brake control, lick sensing, reward spout control, timing, sound output, and serial logging.

At startup, the firmware waits for a handshake from the Python app. During a session it emits event messages, encoder updates, and control messages back over serial.

### 3. Runtime/configuration folders

- `config/` contains files used at runtime, such as animal/cohort mappings, Google credentials, and environment values.
- `config/update.json` controls optional startup syncing from a GitHub manifest.
- `config/update_manifest.example.json` shows the manifest format expected by the startup updater.
- `logs/errors.log` stores runtime exception logs.
- `data/raw/` stores raw capacitive capture exports.
- `data/sessions/` stores local fallback session saves if remote saving fails.

### 4. Packaging/build files

- `launcher.py` is the stable bootstrapper entry point used by PyInstaller.
- `build.ps1` creates a virtual environment, installs dependencies, builds the stable launcher, builds the versioned client bundle, and stages release artifacts.
- `mousetrainer.spec` builds the stable `MouseTrainer.exe` launcher.
- `mousetrainer_client.spec` builds the versioned `MouseTrainerClient` bundle that the launcher installs and runs.

## How the project works during a session

At a high level:

1. The operator starts the Python application.
2. The app optionally uploads firmware in development mode.
3. The app connects to the Arduino and sends configuration values such as phase, thresholds, brake timings, spout pulse duration, and side settings.
4. The firmware runs the behavioral state machine and reports messages back over serial.
5. The Python app collects events and encoder data, updates the cursor display for wheel tasks, optionally starts/stops imaging, and tracks trial outcomes.
6. At the end of the session, the app saves data remotely and/or locally, writes logs, and performs cleanup.

## How to use the project files

### Prerequisites

This project is set up for Windows/PowerShell. Typical requirements are:

- Python 3.11+ for source runs
- Python 3.12 for the current packaged build flow
- An Arduino Mega and `arduino-cli` if you want automatic compile/upload during development
- Required Python packages from `requirements.txt`
- Valid runtime config files in `config/`
- A reachable imaging server if imaging integration is enabled

### Development run from source

From the repository root:

```powershell
.\run.bat
```

This calls `tools\dev_run.ps1`, which:

- sets `PYTHONPATH` to `src`
- optionally compiles/uploads the Arduino firmware if `arduino-cli` and a compatible board are available
- launches the app with `python -m mousetrainer`

If you want to skip firmware upload during development:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\dev_run.ps1 -SkipFirmwareUpload
```

### Main runtime files

- Edit `config/animal_map.json` to map animals to cohort/workbook groups.
- Provide `config/credentials.json` for Google API access if remote saving is used.
- Provide `config/.env` for environment variables such as workbook IDs, SMTP settings, brake/spout timing, and other runtime settings.
- Check `data/` and `logs/` after test runs to inspect outputs and failures.

### Firmware-only workflow

If you want to work on just the hardware side, open `firmware/behavioral_controller/` with Arduino tooling or use `arduino-cli` directly to compile and upload the sketch to the target board.

## Creating a standalone distribution

The project now uses a professional-style bootstrapper layout:

- `MouseTrainer.exe` is a stable launcher that stays at the install root on each client machine.
- The actual application code and bundled dependencies live under `app\versions\<version>\`.
- At startup, the launcher can download a newer versioned bundle, activate it, and then launch that bundle against the same local `config\`, `data\`, and `logs\` folders.

### Build steps

From the repository root:

```powershell
.\build.ps1 -Clean
```

What the script does:

1. Deletes old `build/` and `dist/` output when `-Clean` is provided.
2. Creates `.venv` with `py -3.12` if needed.
3. Verifies that the virtual environment is using Python 3.12.
4. Installs dependencies from `requirements.txt`.
5. Installs `pyinstaller`.
6. If `mouse.png` exists, installs `pillow` and converts the image into a Windows `.ico`.
7. Builds the stable launcher defined by `mousetrainer.spec`.
8. Builds the versioned client bundle defined by `mousetrainer_client.spec`.
9. Stages a ready-to-ship app folder and a release zip for hosted updates.

### Build output

The main output files are:

```text
dist\MouseTrainer.exe
dist\MouseTrainerClient\
dist\USE_THIS\
export\packages\MouseTrainerClient-<version>-win64.zip
```

### Exporting to another computer

To move the app to another Windows machine, copy:

- `dist\USE_THIS\MouseTrainer.exe`
- `dist\USE_THIS\app\`
- `dist\USE_THIS\config\`
- or use the refreshed `export\` folder, which carries the same launcher/config/runtime layout plus the release zip used for hosted updates

At runtime, the app writes:

- logs to `logs\errors.log`
- raw data to `data\raw\`
- fallback session saves to `data\sessions\`

If the destination computer will actually run experiments, make sure it also has:

- the correct Arduino connected
- access to any required network resources
- valid config and credential files
- any imaging-side software/services required by `TCPClient.py`

## Notes for a public GitHub repository

Before pushing this project publicly, review these items carefully:

- `config/credentials.json`
- `config/.env` if present
- `config/update.json`
- any workbook IDs, API tokens, SMTP passwords, or internal hostnames/IPs
- any generated `data/`, `logs/`, `build/`, `dist/`, or `__pycache__/` contents you do not want versioned

In most public repositories, it is better to commit:

- source code
- firmware
- build scripts
- sanitized example config files
- `config/update_manifest.json` only if it references non-secret files

and exclude:

- secrets
- local output data
- local logs
- generated build artifacts

## Startup updates

The packaged app now uses a launcher-plus-bundle update model instead of patching the running executable in place.

- When the packaged launcher starts, it shows a splash screen before the session console opens.
- The launcher reads `config/update.json`, checks the hosted manifest, and keeps the client running even if the network is down or the manifest is invalid.
- The updater syncs non-sensitive config files into `.\config\` before `behavioral_master.py` reads `animal_map.json`, `.env`, and related settings.
- By default, `.env` and `credentials.json` are never pulled from the manifest unless `allow_sensitive_config_sync` is explicitly enabled.
- When the manifest advertises a newer client bundle, the launcher downloads a zip package, verifies its SHA-256 hash, extracts it into `.\app\versions\`, marks it active in `.\app\active.json`, and launches that version.
- Local config, logs, and data remain outside the versioned bundle, so updates do not overwrite each client machine's local runtime state.
- The manifest can also publish a newer `MouseTrainer.exe` launcher for rare bootstrapper updates.

To generate a manifest locally, use:

```powershell
.\.venv\Scripts\python.exe .\tools\generate_update_manifest.py `
  --repo OWNER/REPO `
  --ref main `
  --out .\config\update_manifest.json `
  --config-file animal_map.json `
  --config-file remote_status.json `
  --app-version 0.1.0 `
  --package-path .\export\packages\MouseTrainerClient-0.1.0-win64.zip `
  --package-url https://github.com/OWNER/REPO/releases/download/v0.1.0/MouseTrainerClient-0.1.0-win64.zip `
  --launch-exe MouseTrainerClient.exe `
  --bundle-dir MouseTrainerClient-0.1.0 `
  --launcher-version 0.1.0 `
  --launcher-path .\export\MouseTrainer.exe `
  --launcher-url https://github.com/OWNER/REPO/releases/download/v0.1.0/MouseTrainer.exe
```

## Useful files to start with

If you are new to the codebase, read these first:

1. `src/mousetrainer/behavioral_master.py`
2. `firmware/behavioral_controller/behavioral_controller.ino`
3. `src/mousetrainer/cursor_utils.py`
4. `src/mousetrainer/TCPClient.py`
5. `build.ps1`
6. `mousetrainer.spec`
