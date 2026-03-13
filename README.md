
Lightweight OSINT/recon tool (subdomain enumeration, Wayback scanning, enrichment). This README explains how to configure the project using a `.env` file, install dependencies, and run the core runner on Windows PowerShell.




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


bhai ab iska ui bhi add kr diya h core.webapp karke run ho jayega 

```powershell
# Compile check (recommended before first run)
python -m compileall . -q

# Verbose compile check (to see all files being processed)
python -m compileall .
```

The `compileall` tool scans all Python files and reports any syntax errors. A successful run (exit code 0) means the code is ready to execute.




### Combined example: Full scan with all safety flags
```powershell
python -m core.main example.com --use-st --use-otx --enrich --subs --no-discord --no-empty-notify --verbose
```









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
