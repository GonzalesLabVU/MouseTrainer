from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a MouseTrainer startup update manifest.")
    parser.add_argument("--repo", required=True, help="GitHub repo slug, for example OWNER/REPO")
    parser.add_argument("--ref", default="main", help="Git ref used for raw config downloads")
    parser.add_argument("--out", required=True, help="Output manifest path")
    parser.add_argument("--channel", default="stable", help="Manifest channel label")
    parser.add_argument("--config-version", default="", help="Optional config version label")
    parser.add_argument(
        "--config-file",
        action="append",
        default=[],
        help="Config file relative to the local config directory, repeat as needed",
    )
    parser.add_argument("--config-root", default="config", help="Local config directory")
    parser.add_argument("--app-version", default="", help="Optional bundled app version")
    parser.add_argument("--package-path", default="", help="Local app package zip path to hash")
    parser.add_argument("--package-url", default="", help="Published download URL for the app package zip")
    parser.add_argument(
        "--launch-exe",
        default="MouseTrainerClient.exe",
        help="Executable inside the installed release directory that the launcher should run",
    )
    parser.add_argument(
        "--bundle-dir",
        default="",
        help="Top-level directory name expected inside the downloaded app package zip",
    )
    parser.add_argument("--launcher-version", default="", help="Optional launcher version")
    parser.add_argument("--launcher-path", default="", help="Local launcher exe path to hash")
    parser.add_argument("--launcher-url", default="", help="Published download URL for the launcher exe")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_root = Path(args.config_root).resolve()

    manifest: dict[str, object] = {
        "manifest_version": 2,
        "channel": args.channel,
        "generated_at": utc_now(),
        "config": {
            "version": args.config_version or utc_now(),
            "files": [],
        },
    }

    config_files: list[dict[str, str]] = []
    for relative_value in args.config_file:
        relative_path = Path(relative_value)
        absolute_path = (config_root / relative_path).resolve()
        if not absolute_path.exists():
            raise FileNotFoundError(f"config file not found: {absolute_path}")

        config_files.append(
            {
                "path": relative_path.as_posix(),
                "url": f"https://raw.githubusercontent.com/{args.repo}/{args.ref}/config/{relative_path.as_posix()}",
                "sha256": sha256_file(absolute_path),
            }
        )

    manifest["config"]["files"] = config_files

    if args.app_version and args.package_path and args.package_url:
        package_path = Path(args.package_path).resolve()
        if not package_path.exists():
            raise FileNotFoundError(f"app package not found: {package_path}")

        manifest["app"] = {
            "version": args.app_version,
            "package_url": args.package_url,
            "package_sha256": sha256_file(package_path),
            "launch_exe": args.launch_exe,
            "bundle_dir": args.bundle_dir or args.app_version,
        }

    if args.launcher_version and args.launcher_path and args.launcher_url:
        launcher_path = Path(args.launcher_path).resolve()
        if not launcher_path.exists():
            raise FileNotFoundError(f"launcher exe not found: {launcher_path}")

        manifest["launcher"] = {
            "version": args.launcher_version,
            "url": args.launcher_url,
            "sha256": sha256_file(launcher_path),
        }

    output_path = Path(args.out).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=False)
        f.write("\n")

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
