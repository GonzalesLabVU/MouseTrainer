# Build And Ship

Project layout:

- `src/mousetrainer`: Python application package
- `config`: runtime configuration and credentials
- `firmware/behavioral_controller`: Arduino sketch
- `data`: locally saved session output
- `logs`: runtime logs
- `tools`: developer scripts

Development run:

```powershell
.\run.bat
```

Build the packaged launcher and client bundle:

```powershell
.\build.ps1 -Clean
```

The build script now:

- creates `.venv` automatically with `py -3.12`
- installs `requirements.txt`
- installs `pyinstaller`
- installs `pillow` automatically when `mouse.png` exists in the project root
- builds the stable launcher at `dist\MouseTrainer.exe`
- builds the versioned client bundle at `dist\MouseTrainerClient\`
- refreshes `dist\USE_THIS\MouseTrainer.exe`
- refreshes `dist\USE_THIS\app\active.json`
- refreshes `dist\USE_THIS\app\versions\<version>\`
- refreshes `dist\USE_THIS\config\`
- refreshes `export\MouseTrainer.exe`
- refreshes `export\app\active.json`
- refreshes `export\app\versions\<version>\`
- refreshes `export\config\`
- writes the hosted update package zip to `export\packages\`

If Python 3.12 is not installed, the script stops with a clear error.

Custom icon:

- put `mouse.png` in the project root
- `.\build.ps1 -Clean` converts it to a multi-size `.ico` and embeds that in both the launcher and the client bundle executable

Files to ship to a client computer:

- `dist\USE_THIS\MouseTrainer.exe`
- `dist\USE_THIS\app\`
- `dist\USE_THIS\config\`

Files to publish for hosted updates:

- `export\MouseTrainer.exe` for optional launcher self-updates
- `export\packages\MouseTrainerClient-<version>-win64.zip` for client bundle updates
- `config\update_manifest.json` once it points at the published URLs

Runtime behavior:

- the packaged app uses a stable windowed launcher that shows a startup splash
- editable config is resolved from `.\config\` beside the launcher first
- the launcher installs and activates versioned client bundles under `.\app\versions\`
- the active client bundle reads and writes runtime data from the install root, not from inside the bundle directory
- optional startup updates can pull config files from a GitHub-hosted manifest before the main app loads
- optional app updates can download a newer client bundle zip, activate it locally, and launch it immediately
- optional launcher updates can replace `MouseTrainer.exe` and restart
- logs are written to `.\logs\errors.log`
- raw captures are written to `.\data\raw\`
- fallback session saves are written to `.\data\sessions\`
