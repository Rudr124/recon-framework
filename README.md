# KALU | BHAI — Recon Framework

Lightweight OSINT/recon tool (subdomain enumeration, Wayback scanning, enrichment). This README explains how to configure the project using a `.env` file, install dependencies, and run the core runner on Windows PowerShell.

## Quick summary
- Subdomain enumeration (crt.sh, optional SecurityTrails / OTX / Shodan)
- Wayback Machine URL harvesting and filtering (200/403)
- Enrichment via modular `parsers/` (WHOIS, DNS, Shodan, URLScan, etc.)
- Notifications via Discord webhooks (configured through environment variables)


## Setup (Windows PowerShell)
1. Create a Python virtual environment (recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

3. Configure secrets via `.env`:

```powershell
Copy-Item .env.example .env
notepad .env    # or your preferred editor, then fill values
```

Important env variables (put real values into `.env`):
- DISCORD_HOOK_SUBDOMAINS
- DISCORD_HOOK_WAYBACK
- DISCORD_HOOK_ENRICHMENT
- SECURITYTRAILS_KEY
- OTX_KEY
- SHODAN_KEY
- VIRUSTOTAL_KEY

Do NOT commit your `.env` file. `.gitignore` includes `.env` by default.


## Running
From the repository root (PowerShell) you can run the core CLI:

```powershell
python -m core.main example.com --use-st --use-otx --enrich
```

New flags available on `core.main`:

- `--no-discord` : Do not post any results to Discord (useful for testing/CI).
- `--verbose` : Enable more verbose logging to the console.

Flags of interest:
- `--subs` include discovered subdomains in Wayback scanning
- `--no-wayback` skip Wayback
- `--use-st` use SecurityTrails (requires key in env)
- `--use-otx` use AlienVault OTX (requires key in env)
- `--enrich` run enrichment parsers after discovery


## Notes & Security
- The code now loads sensitive values from environment variables (.env) using `python-dotenv` if available.
- I intentionally did not modify `recon.py` or `recon2.py` (per your request). Those files still contain hard-coded webhooks in the repository; if those are live, rotate them immediately.
  - To rotate: go to the Discord webhook settings and create new webhooks, then update `.env` and do not commit the new webhook URL.

## Compilation & Validation
Before running the tool, you should validate the codebase for syntax errors:

```powershell
# Compile check (recommended before first run)
python -m compileall . -q

# Verbose compile check (to see all files being processed)
python -m compileall .
```

The `compileall` tool scans all Python files and reports any syntax errors. A successful run (exit code 0) means the code is ready to execute.


## Command Reference & Examples

### Basic subdomain enumeration (crt.sh only)
```powershell
python -m core.main example.com
```
**Output:** Saves unique subdomains to `output/subs_example.com_<timestamp>.txt`

### Enumerate with SecurityTrails + OTX
```powershell
python -m core.main example.com --use-st --use-otx
```
**Requires:** `SECURITYTRAILS_KEY` and `OTX_KEY` in `.env`

### Full recon with enrichment (DNS, WHOIS, URLScan, Shodan)
```powershell
python -m core.main example.com --use-st --use-otx --enrich
```
**Requires:** Keys for SecurityTrails, OTX, URLScan, Shodan in `.env`
**Output:** Saves subs + enrichment data; posts to Discord if webhooks configured

### Scan Wayback Machine for live URLs
```powershell
python -m core.main example.com --use-st --use-otx --enrich --subs
```
**What it does:** Finds Wayback URLs for subdomains and filters those returning HTTP 200 or 403
**Output:** Saves wayback URLs to `output/wayback_<domain>_<timestamp>.txt`

### Skip Wayback (faster scan, no URLs)
```powershell
python -m core.main example.com --use-st --use-otx --enrich --no-wayback
```

### Test mode (no Discord posts)
```powershell
python -m core.main example.com --use-st --use-otx --enrich --no-discord
```
**Use case:** Safe testing; results are saved but not posted to Discord

### Suppress empty result notifications
```powershell
python -m core.main example.com --use-st --use-otx --enrich --no-empty-notify
```
**Use case:** Don't post to Discord if a source returns zero results

### Verbose logging (for debugging)
```powershell
python -m core.main example.com --use-st --use-otx --enrich --verbose
```
**Output:** Prints detailed progress and API responses to console

### Combined example: Full scan with all safety flags
```powershell
python -m core.main example.com --use-st --use-otx --enrich --subs --no-discord --no-empty-notify --verbose
```







## Troubleshooting
- If you see errors about `module not found` when running `python -m core.main`, ensure you are running from the repository root and that `core/__init__.py` exists (it does in this repo).
- **"No API key provided"** errors for URLScan, Shodan, etc.?
  - Check your `.env` file has the correct variable names (see table above).
  - Ensure `.env` is in the repo root, not in a subdirectory.
- **Syntax errors on startup?**
  - Run `python -m compileall . -q` to identify which file has the issue.
- **Discord posts not appearing?**
  - Verify webhook URL in `.env` is correct and still valid (webhooks expire).
  - Run with `--verbose` to see HTTP responses from Discord.
- **Timeouts on Wayback or API calls?**
  - Increase `REQUEST_TIMEOUT` in `.env` (e.g., `60` for slower networks).
  - Run with `--no-wayback` to skip Wayback if it's hanging.

## Quick Start Example
Get started immediately with this tested command:

```powershell
# Before first run, validate syntax
python -m compileall . -q

# Then run a test scan
python -m core.main example.com --use-st --use-otx --enrich --no-discord --verbose
```

**Expected output:**
- Console prints: subdomain counts, parser results, file paths
- Files created: `output/subs_example.com_<timestamp>.txt` with merged subdomains
- No Discord posts (because of `--no-discord`)

Once you've verified the tool works, remove `--no-discord` to enable Discord notifications for real scans.

python -c "from parsers import portscanner_parser as p; print(p.run('example.com'))"