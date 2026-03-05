# spotseek 🎵

Automatically download your Spotify playlists via Soulseek with a single command.

## Features

- ✅ Fetch any **public Spotify playlist** (no user login needed)
- ✅ Smart search: tries **extended versions first**, falls back to **original mix**
- ✅ Downloads as **FLAC or MP3** (your choice)
- ✅ Real-time progress display
- ✅ Summary report (downloaded, failed, extended vs original)
- ✅ Config file support (skip prompts with `.env`)

## Prerequisites

- Python 3.9+
- Spotify API credentials (free, takes 2 min)
- Soulseek account
- `sldl` (slsk-batchdl) binary

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/soulseek-maxer.git
cd soulseek-maxer
```

### 2. Create Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Get Spotify API credentials (2 minutes)

1. Go to https://developer.spotify.com/dashboard
2. Log in (create free account if needed)
3. Click "Create an App"
4. Accept terms → create
5. Copy your **Client ID** and **Client Secret**

### 4. Get `sldl` binary

**Option A: Download pre-built (recommended)**

```bash
# Create the sldl app directory
mkdir -p sldl_app
cd sldl_app

# Download latest release for your system
# For macOS ARM64 (Apple Silicon):
curl -L https://github.com/fiso64/slsk-batchdl/releases/latest/download/sldl_osx-arm64.zip -o sldl.zip

# For macOS Intel:
# curl -L https://github.com/fiso64/slsk-batchdl/releases/latest/download/sldl_osx-x64.zip -o sldl.zip

# For Linux:
# curl -L https://github.com/fiso64/slsk-batchdl/releases/latest/download/sldl_linux-x64.zip -o sldl.zip

# Unzip and extract sldl
unzip sldl.zip
rm sldl.zip
cd ..

# Make executable (macOS/Linux only)
chmod +x sldl_app/sldl
```

**Option B: Build from source**

```bash
# Clone slsk-batchdl
git clone https://github.com/fiso64/slsk-batchdl.git
cd slsk-batchdl
dotnet publish -c Release -o publish

# Copy to spotseek project
cp -r publish ../soulseek-maxer/sldl_app
cd ..
```

### 5. Configure with `.env` file

```bash
# Copy the template
cp .env.example .env

# Edit with your credentials
nano .env
```

Fill in:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_PLAYLIST_URL=https://open.spotify.com/playlist/...
SOULSEEK_USERNAME=your_username
SOULSEEK_PASSWORD=your_password
OUTPUT_DIRECTORY=~/Music/downloads
PREFERRED_FORMAT=flac
```

## Usage

```bash
python3 spotseek.py
```

The script will:
1. Fetch your Spotify playlist
2. Search Soulseek for each track (extended first, original as fallback)
3. Download to your output directory
4. Show a summary report

### Interactive mode

If you don't use `.env`, the script will prompt for:
- Spotify playlist URL
- Audio format (FLAC/MP3)
- Soulseek username & password
- Output directory

### Example output

```
╔══════════════════════════════════╗
║  spotseek – Spotify → Soulseek   ║
╚══════════════════════════════════╝

Fetching playlist from Spotify…
  'Energy Hits' — 137 tracks

Pass 1/2  Searching for extended versions…
Pass 2/2  Falling back to original mix for 21 track(s)…

──────────────────────────────────────────
  DOWNLOAD SUMMARY
──────────────────────────────────────────
  Total tracks         : 137
  Downloaded           : 116
    ├─ Extended versions : 75
    └─ Original versions : 41
  Failed / not found   : 21

  Files saved to: ~/Music/downloads
──────────────────────────────────────────
```

## Troubleshooting

### "sldl executable not found"

Make sure `sldl_app/sldl` exists:
```bash
ls -la sldl_app/sldl
chmod +x sldl_app/sldl
```

### "Permission denied: sldl" (macOS)

Remove quarantine attribute:
```bash
xattr -d com.apple.quarantine sldl_app/sldl
```

### "Input error: Unknown argument"

Your `sldl` version might be older. Download the latest release from:
https://github.com/fiso64/slsk-batchdl/releases

### "Failed to authenticate with Spotify"

Double-check your Client ID/Secret in `.env` are correct (copy-paste from Spotify dashboard)

### "Soulseek login failed"

Verify your Soulseek username and password work by logging in at https://www.slsknet.org/

## How it works

1. **Fetch playlist** - Uses official Spotify API to get all tracks
2. **Search extended** - Searches Soulseek for "artist title extended"
3. **Fallback** - For tracks not found, retries with "artist title original mix"
4. **Download** - Uses `sldl` (slsk-batchdl) for actual Soulseek downloads
5. **Summary** - Counts extended vs original versions downloaded

## Configuration

See `.env.example` for all available options:
- `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` - Spotify API credentials
- `SPOTIFY_PLAYLIST_URL` - Public playlist URL
- `SOULSEEK_USERNAME` / `SOULSEEK_PASSWORD` - Soulseek login
- `OUTPUT_DIRECTORY` - Where to save files
- `PREFERRED_FORMAT` - `flac` or `mp3`

## Requirements

- Python 3.9+
- `requests` - HTTP library
- `spotipy` - Spotify API client
- `python-dotenv` - Config file support
- `sldl` (slsk-batchdl) - Soulseek batch downloader

## License

MIT

## Credits

- [slsk-batchdl](https://github.com/fiso64/slsk-batchdl) - Batch download from Soulseek
- [Spotify API](https://developer.spotify.com/) - Playlist data

## Support

For issues with Soulseek downloads, see [slsk-batchdl docs](https://github.com/fiso64/slsk-batchdl#readme)

For Spotify API help, see [Spotify Developer Docs](https://developer.spotify.com/documentation/web-api)
