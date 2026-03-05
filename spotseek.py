#!/usr/bin/env python3
"""
spotseek – Download a public Spotify playlist via Soulseek (slsk-batchdl / sldl)

Configuration via .env file or interactive prompts. See .env.example for template.

Usage:
    python spotseek.py

Dependencies:
    pip install requests python-dotenv spotipy
"""

import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from getpass import getpass
from pathlib import Path

try:
    import requests
    from dotenv import load_dotenv
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError as e:
    sys.exit(f"Missing dependency: {e}\nRun: pip install requests python-dotenv spotipy")


# ─────────────────────────────────────────────────────────────────────────────
# Config helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_config():
    """Load .env file from current directory."""
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)


def get_config(key: str, prompt: str, choices: list[str] | None = None,
               default: str | None = None, secret: bool = False) -> str:
    """Get a config value from environment or prompt the user."""
    val = os.getenv(key)
    if val:
        return val.lower() if choices else val

    # Prompt user
    hint = (
        f" [{default}]"
        if default
        else (f" ({'/'.join(choices)})" if choices else "")
    )
    while True:
        fn = getpass if secret else input
        ans = fn(f"{prompt}{hint}: ").strip()
        if not ans and default is not None:
            return default
        if choices is None or ans.lower() in choices:
            return ans.lower() if choices else ans
        print(f"  → Please enter one of: {', '.join(choices)}")


# ─────────────────────────────────────────────────────────────────────────────
# Spotify – official API with client credentials
# ─────────────────────────────────────────────────────────────────────────────

def fetch_playlist(playlist_id: str, client_id: str, client_secret: str) -> tuple[str, list[dict]]:
    """Return (playlist_name, tracks) using official Spotify API.
    Each track dict has keys: title, artist, album, length (seconds).
    """
    try:
        sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
        )
    except Exception as e:
        raise RuntimeError(f"Failed to authenticate with Spotify API: {e}")

    try:
        playlist = sp.playlist(playlist_id, fields="name")
        name = playlist.get("name", "Unknown Playlist")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch playlist: {e}")

    tracks: list[dict] = []
    results = sp.playlist_tracks(playlist_id, limit=100)

    while results:
        for item in results.get("items", []):
            t = item.get("track")
            if t and t.get("name"):
                tracks.append(
                    {
                        "title": t["name"],
                        "artist": (t.get("artists") or [{}])[0].get("name", "Unknown"),
                        "album": (t.get("album") or {}).get("name", ""),
                        "length": t.get("duration_ms", 0) // 1000,
                    }
                )

        if results.get("next"):
            results = sp.next(results)
        else:
            break

    return name, tracks


def parse_playlist_id(url: str) -> str | None:
    m = re.search(r"playlist/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# File matching helpers
# ─────────────────────────────────────────────────────────────────────────────

AUDIO_EXTS = {".flac", ".mp3", ".ogg", ".m4a", ".wav", ".aiff"}

_PUNCT = re.compile(r"[^\w\s]")
_NOISE = re.compile(
    r"\b(extended|mix|version|edit|remix|original|club|radio|"
    r"instrumental|feat|ft|the|a|an)\b",
    re.I,
)
_SPACE = re.compile(r"\s+")


def _norm(s: str) -> str:
    s = _PUNCT.sub(" ", s.lower())
    s = _NOISE.sub(" ", s)
    return _SPACE.sub(" ", s).strip()


def _strip_remix(title: str) -> str:
    """Remove 'remix'/'mix' keywords but keep artist info.
    E.g., 'Delicate - REBRN Remix' -> 'Delicate - REBRN'
    """
    # Remove word "remix" and "mix" at the end (but keep the artist name before it)
    title = re.sub(r'\s+(remix|mix|version|edit|remaster)\b', '', title, flags=re.I)
    # Clean up multiple spaces
    title = re.sub(r'\s+', ' ', title)
    return title.strip()


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def audio_files(directory: Path) -> set[Path]:
    return {f for f in directory.rglob("*") if f.suffix.lower() in AUDIO_EXTS}


def is_extended(path: Path) -> bool:
    return bool(re.search(r"\bextended\b", path.stem, re.I))


def track_found_in(track: dict, files: set[Path]) -> bool:
    """Return True if *files* contains a plausible download of *track*."""
    title_n = _norm(track["title"])
    artist_n = _norm(track["artist"])
    for f in files:
        stem = _norm(f.stem)

        # Title match: exact substring or high similarity
        title_ok = title_n in stem or _sim(title_n, stem) > 0.75

        # Artist match: substring (in case multiple artists), or similarity
        artist_ok = artist_n in stem or _sim(artist_n, stem) > 0.65

        # At least one version of the artist must match
        if title_ok and artist_ok:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CSV helpers
# ─────────────────────────────────────────────────────────────────────────────

def write_csv(tracks: list[dict], path: Path, *, extended: bool = False) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["title", "artist", "album", "length"])
        for t in tracks:
            # Always search for extended versions by appending to title
            # This biases Soulseek search toward extended mixes
            title = t["title"] + " extended"
            w.writerow([title, t["artist"], t["album"], t["length"]])


# ─────────────────────────────────────────────────────────────────────────────
# sldl helpers
# ─────────────────────────────────────────────────────────────────────────────

def find_sldl() -> str | None:
    # Check local app directory first
    if Path("./sldl_app/sldl").is_file():
        return "./sldl_app/sldl"
    # Then check local directory
    for c in ("./sldl", "./sldl.exe", "sldl", "sldl.exe"):
        if Path(c).is_file():
            return c
        if shutil.which(c):
            return c
    return None


def install_sldl() -> str:
    """Download sldl from GitHub releases for the current platform."""
    import platform
    import zipfile

    print("  Downloading sldl from GitHub releases…")

    # Detect platform and architecture
    system = platform.system()  # "Darwin" (macOS), "Linux", "Windows"
    machine = platform.machine()  # "arm64", "x86_64", "AMD64"

    if system == "Darwin":
        if machine == "arm64":
            asset_pattern = r"sldl-osx-arm64"
        else:
            asset_pattern = r"sldl-osx-x64"
    elif system == "Linux":
        asset_pattern = r"sldl-linux-x64"
    elif system == "Windows":
        asset_pattern = r"sldl-win-x64\.exe"
    else:
        raise RuntimeError(f"Unsupported platform: {system}")

    # Get latest release from GitHub API
    try:
        r = requests.get(
            "https://api.github.com/repos/fiso64/slsk-batchdl/releases/latest",
            timeout=10,
        )
        r.raise_for_status()
        release = r.json()
    except Exception as e:
        raise RuntimeError(f"Failed to fetch sldl releases from GitHub: {e}")

    # Find matching asset
    asset = None
    for a in release.get("assets", []):
        if re.search(asset_pattern, a["name"], re.IGNORECASE):
            asset = a
            break

    if not asset:
        available = ", ".join(a["name"] for a in release.get("assets", [])[:5])
        raise RuntimeError(
            f"No matching sldl release found for {system}/{machine}.\n"
            f"Available: {available}"
        )

    # Download to ~/.local/bin/sldl
    install_dir = Path.home() / ".local" / "bin"
    install_dir.mkdir(parents=True, exist_ok=True)

    sldl_path = install_dir / ("sldl.exe" if system == "Windows" else "sldl")

    print(f"  Downloading {asset['name']}…")
    try:
        r = requests.get(asset["browser_download_url"], timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Failed to download sldl: {e}")

    # Handle .zip files (self-contained releases)
    if asset["name"].endswith(".zip"):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(r.content)
            tmp_path = tmp.name

        with zipfile.ZipFile(tmp_path, "r") as z:
            # Find the sldl executable in the zip
            exe_name = "sldl.exe" if system == "Windows" else "sldl"
            files = z.namelist()
            exe_file = next((f for f in files if f.endswith(exe_name)), None)
            if not exe_file:
                raise RuntimeError(f"sldl executable not found in release zip")
            z.extract(exe_file, install_dir)
            extracted = install_dir / exe_file
            if extracted != sldl_path:
                extracted.rename(sldl_path)

        Path(tmp_path).unlink()
    else:
        # Binary file (not zipped)
        sldl_path.write_bytes(r.content)

    # Make executable on Unix
    if system != "Windows":
        sldl_path.chmod(0o755)

    print(f"  Installed sldl to {sldl_path}")
    return str(sldl_path)


def run_sldl(
    sldl: str,
    csv_path: Path,
    out_dir: Path,
    user: str,
    password: str,
    fmt: str,
    extra: list[str] | None = None,
) -> int:
    """Invoke sldl and stream output in real-time."""
    cmd = [
        sldl,
        str(csv_path),
        "--user", user,
        "--pass", password,
        "--path", str(out_dir),
        "--pref-format", fmt,
        "--name-format", "{artist} - {title}",
    ]
    if extra:
        cmd.extend(extra)

    # Run with real-time output streaming
    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        print(f"  ⚠ sldl exited with code {result.returncode}")

    return result.returncode


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    load_config()

    # Check for debug mode
    debug = "--debug" in sys.argv

    print("╔══════════════════════════════════╗")
    print("║  spotseek – Spotify → Soulseek   ║")
    print("╚══════════════════════════════════╝\n")

    # ── Spotify API credentials ───────────────────────────────────────────────
    client_id = get_config(
        "SPOTIFY_CLIENT_ID",
        "Spotify Client ID (get free from developer.spotify.com)",
    )
    client_secret = get_config(
        "SPOTIFY_CLIENT_SECRET",
        "Spotify Client Secret",
        secret=True,
    )

    # ── Playlist ──────────────────────────────────────────────────────────────
    playlist_url = get_config(
        "SPOTIFY_PLAYLIST_URL",
        "Spotify playlist URL",
    )
    playlist_id = parse_playlist_id(playlist_url)
    if not playlist_id:
        sys.exit("Could not parse a playlist ID from that URL.")

    # ── Download format ───────────────────────────────────────────────────────
    fmt = get_config(
        "PREFERRED_FORMAT",
        "Preferred format",
        ["flac", "mp3"],
        default="flac",
    )

    # ── Soulseek credentials ──────────────────────────────────────────────────
    sl_user = get_config(
        "SOULSEEK_USERNAME",
        "Soulseek username",
    )
    sl_pass = get_config(
        "SOULSEEK_PASSWORD",
        "Soulseek password",
        secret=True,
    )

    # ── Output directory ──────────────────────────────────────────────────────
    out_dir = Path(
        get_config(
            "OUTPUT_DIRECTORY",
            "Output directory",
            default="./downloads",
        )
    ).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Locate sldl ───────────────────────────────────────────────────────────
    sldl = find_sldl()
    if not sldl:
        try:
            sldl = install_sldl()
        except Exception as e:
            sys.exit(f"Failed to install sldl: {e}")

    # ── Fetch playlist from Spotify ───────────────────────────────────────────
    print("\nFetching playlist from Spotify…")
    try:
        playlist_name, tracks = fetch_playlist(playlist_id, client_id, client_secret)
    except Exception as exc:
        sys.exit(f"Failed to fetch playlist: {exc}")

    # Filter out tracks with "radio" in the title
    tracks = [t for t in tracks if "radio" not in t["title"].lower()]

    total = len(tracks)
    if total == 0:
        sys.exit("Playlist is empty or could not be read.")

    # Optionally limit tracks for debugging
    max_tracks = os.getenv("MAX_TRACKS")
    if max_tracks:
        try:
            limit = int(max_tracks)
            if limit > 0:
                tracks = tracks[:limit]
                total = len(tracks)
                print(f"  '{playlist_name}' — {total} tracks (limited by MAX_TRACKS)")
            else:
                print(f"  '{playlist_name}' — {total} tracks\n")
        except ValueError:
            print(f"  Warning: MAX_TRACKS invalid, using all {total} tracks\n")
    else:
        print(f"  '{playlist_name}' — {total} tracks\n")

    # ── Download ──────────────────────────────────────────────────────────────
    print("Downloading tracks…\n")

    with tempfile.TemporaryDirectory() as _tmp:
        tmp = Path(_tmp)
        all_files = set()

        # ── Pass 1: Try extended versions ─────────────────────────────────────
        print("Pass 1/3  Searching for extended versions…")
        pass1_dir = tmp / "pass1"
        pass1_dir.mkdir()
        csv1 = tmp / "extended.csv"
        with open(csv1, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["title", "artist", "album", "length"])
            for t in tracks:
                # Strip remix info from title, then add "extended"
                base_title = _strip_remix(t["title"])
                title = base_title + " extended"
                w.writerow([title, t["artist"], t["album"], t["length"]])

        if debug:
            print(f"  Debug: Pass 1 search terms (first 3):")
            with open(csv1, "r") as fh:
                reader = csv.reader(fh)
                next(reader)  # skip header
                for i, row in enumerate(reader):
                    if i >= 3:
                        break
                    print(f"    {row[1]} - {row[0]}")

        run_sldl(
            sldl, csv1, pass1_dir, sl_user, sl_pass, fmt,
        )

        files_1 = audio_files(pass1_dir)
        all_files.update(files_1)

        # ── Pass 2: Try original mix for what wasn't found ────────────────────
        not_found = [t for t in tracks if not track_found_in(t, files_1)]
        if not_found:
            print(f"\nPass 2/3  Searching for original mix versions for {len(not_found)} track(s)…")
            pass2_dir = tmp / "pass2"
            pass2_dir.mkdir()
            csv2 = tmp / "original.csv"
            with open(csv2, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                w.writerow(["title", "artist", "album", "length"])
                for t in not_found:
                    base_title = _strip_remix(t["title"])
                    title = base_title + " original"
                    w.writerow([title, t["artist"], t["album"], t["length"]])

            run_sldl(
                sldl, csv2, pass2_dir, sl_user, sl_pass, fmt,
            )

            files_2 = audio_files(pass2_dir)
            all_files.update(files_2)

            # ── Pass 3: Fallback to base track name ─────────────────────────
            still_not_found = [t for t in not_found if not track_found_in(t, files_2)]
            if still_not_found:
                print(f"\nPass 3/3  Falling back to base track name for {len(still_not_found)} track(s)…")
                pass3_dir = tmp / "pass3"
                pass3_dir.mkdir()
                csv3 = tmp / "base.csv"
                with open(csv3, "w", newline="", encoding="utf-8") as fh:
                    w = csv.writer(fh)
                    w.writerow(["title", "artist", "album", "length"])
                    for t in still_not_found:
                        base_title = _strip_remix(t["title"])
                        w.writerow([base_title, t["artist"], t["album"], t["length"]])

                run_sldl(
                    sldl, csv3, pass3_dir, sl_user, sl_pass, fmt,
                )

                files_3 = audio_files(pass3_dir)
                all_files.update(files_3)

        # Copy all downloaded files to output directory
        for src_file in all_files:
            dest_file = out_dir / src_file.name
            shutil.copy2(src_file, dest_file)

    new_files = audio_files(out_dir)
    total_files = len(new_files)

    # Count how many tracks have at least one downloaded file
    tracks_found = sum(1 for t in tracks if track_found_in(t, new_files))
    failed_count = total - tracks_found
    not_found_final = [t for t in tracks if not track_found_in(t, new_files)]

    # ── Summary ───────────────────────────────────────────────────────────────
    extended_count = sum(1 for f in new_files if is_extended(f))
    original_count = total_files - extended_count

    print()
    print("─" * 42)
    print("  DOWNLOAD SUMMARY")
    print("─" * 42)
    print(f"  Total tracks         : {total}")
    print(f"  Tracks found         : {tracks_found}")
    print(f"  Total files          : {total_files}")
    if extended_count > 0:
        print(f"    ├─ Extended versions : {extended_count}")
        print(f"    └─ Original versions : {original_count}")
    print(f"  Failed / not found   : {failed_count}")
    print(f"\n  Files saved to: {out_dir.resolve()}")
    print("─" * 42)

    # Print tracks that couldn't be found
    if not_found_final:
        print("\n  Couldn't find:")
        for t in not_found_final:
            print(f"    • {t['artist']} - {t['title']}")


if __name__ == "__main__":
    main()
