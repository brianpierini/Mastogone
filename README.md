# Mastogone

> **Note:** Mastodon only allows 30 deletions every 30 minutes. For large numbers of posts, it's best to run Mastogone as a cron job (see below).

Mastogone is a CLI tool to delete Mastodon posts older than a specified number of days, with advanced filtering, backup, preview, and automation options.

## Motivation

I believe that opinions change, trends fade, and not every thought or post needs to live online forever. As someone who values privacy, I wanted a tool that empowers users to easily and safely clean up their Mastodon history, giving them control over what remains public. Mastogone is designed to make it simple to review, filter, and remove old posts.

## Features

- Export logs
- Verbose and quiet modes
- Cron job friendly
- Advanced filtering (date, keyword, regex, replies, reblogs)
- Backup deleted posts

## Disclaimer

**Warning:** This tool performs irreversible data deletion. Use with caution.  
Double-check your filters and options before running by using `--preview`.

**The `--preview` option will only show what would be deleted and will NOT delete any posts.**  
**The `--no-preview` option will actually delete the matching posts.**

The author is **not responsible** for any data loss or unintended consequences.

## Installation

1. Clone this repo and install dependencies:
    ```zsh
    git clone https://github.com/brianpierini/Mastogone.git
    cd Mastogone
    pip install -r requirements.txt
    # Or, if your system uses pip3:
    pip3 install -r requirements.txt
    ```

2. Create a Mastodon access token:

   1. **Log in to Your Mastodon Instance**

      Go to the web interface of the Mastodon server you’re using (e.g., https://mastodon.social, https://your.instance), and log in to your account.

      ⸻

   2. **Go to Developer Settings**
      - Click on Preferences (gear icon in the sidebar).
      - Scroll down to Development > Click Developer or Developer settings.

      Alternatively, you can go directly to:
      https://your.instance/settings/applications
      (Replace your.instance with your actual Mastodon server domain.)

      ⸻

   3. **Register a New Application**

      Click “New Application” and fill out the form:
      - Application Name: Anything you like (e.g., “Mastogone”).
      - Website (optional): Can leave blank or put a relevant URL.
      - Redirect URI:
        - If you’re using this for a script or bot: use `urn:ietf:wg:oauth:2.0:oob`
      - Scopes: Select the permissions you need:
        - read and write

      Click Submit.

      ⸻

   4. **Get Your Access Token**

      After creating the app, you’ll see:
      - Client ID
      - Client Secret
      - Your Access Token

      Copy the Access Token—this is what you use to authenticate API calls.

> **Note:**  
> Requires Python 3.7 or newer (recommended).

## Quick Start

```zsh
python3 mastogone.py --api-base-url https://mastodon.social
```

- If you just run the script, prompts will guide you through the most important options (like how many days old posts to delete).
- For more in-depth configuration, add the flags outlined below to customize filtering, logging, backup, and more.

- By default, this will **preview** posts older than 30 days.
- To actually delete, add `--no-preview`.
- You will be prompted for your access token, or set it via the `MASTOGONE_TOKEN` environment variable.

## Usage

```zsh
python3 mastogone.py [OPTIONS]
```

### Required

- `--api-base-url`  
  Your Mastodon instance URL (e.g., `https://mastodon.social`).

### Authentication

- Access token:  
  Your Mastodon access token. If omitted, you will be prompted.  
  **Tip:** For automation, set the `MASTOGONE_TOKEN` environment variable.

### Age Filtering

- `--days`, `-d`  
  Delete posts older than this many days.  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 60 --preview
  ```

### Preview Mode

- `--preview/--no-preview`  
  Only show what would be deleted, do not actually delete.  
  Default: `--preview`  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 30 --preview
  ```

### Logging

- `--log-file`, `-l`  
  Override log file name.  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 30 --log-file mylog.txt
  ```

### Keyword/Regex Filtering

- `--match`, `-m`  
  Only delete posts containing this keyword or matching regex. Can be used multiple times.  
  Example (keyword):  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 30 --match hello --match world
  ```
  Example (regex):  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 30 --match '^foo.*bar$' --regex
  ```

- `--regex/--no-regex`  
  Interpret `--match` patterns as regex.  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --days 30 --match 'test\d+' --regex
  ```

### Date Range Filtering

- `--after`  
  Only consider posts after this date (inclusive).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --after 2024-01-01 --preview
  ```

- `--before`  
  Only consider posts before this date (inclusive).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --before 2024-06-01 --preview
  ```

### Backup

- `--backup-file`  
  Backup deleted posts to this JSONL file (default: `deleted_statuses_backup.jsonl`).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --no-preview --backup-file my_backup.jsonl
  ```

### Replies and Reblogs

- `--include-replies/--exclude-replies`  
  Include or exclude replies (default: exclude).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --preview --include-replies
  ```

- `--include-reblogs/--exclude-reblogs`  
  Include or exclude reblogs (default: exclude).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --no-preview --include-reblogs
  ```

### Output Modes

- `--verbose`  
  Enable verbose output (DEBUG logging, show HTTP requests).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --preview --verbose
  ```

- `--quiet`  
  Suppress most output except errors and summary.  
  Progress bars are still shown in quiet mode.  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --no-preview --quiet
  ```

### Rate Limiting and Batch Size

- **Mastodon Delete Rate Limit:**
  - By default, Mastodon only allows 30 delete requests per 30 minutes per account.
  - If you try to delete more, the server will rate limit you (HTTP 429 or silent throttling).
  - Mastogone will automatically pause for 30 minutes after every batch of deletions to respect this limit.

- `--delete-batch-size`  
  Number of deletes before pausing for the rate limit window (default: 30).  
  Example:  
  ```
  python3 mastogone.py --api-base-url https://mastodon.social --no-preview --delete-batch-size 20
  ```
  - If a rate limit error (HTTP 429) is encountered, Mastogone will pause for 30 minutes and retry the failed deletion.

## Running as a Cron Job

You can automate Mastogone to run on a schedule (e.g., nightly) using cron on Linux/macOS servers or hosts.

### 1. Set Up Your Environment
- Make sure your Python virtual environment is activated in your script, or use the full path to python3 and your script.
- Set your `MASTOGONE_TOKEN` environment variable in your crontab or a wrapper script for secure authentication.

### 2. Example Cron Job Entry

This example runs Mastogone every night at 2:30am, deleting posts older than 180 days, in quiet mode, and logs output to a file:

```cron
30 2 * * * cd /path/to/Mastogone && \
  MASTOGONE_TOKEN=your_token_here \
  /usr/bin/env python3 mastogone.py --api-base-url https://mastodon.social --no-preview --days 180 --quiet >> mastogone_cron.log 2>&1
```

- Adjust the path to your Mastogone directory and python3 as needed.
- Use `--quiet` to suppress most output except errors and summary.
- Use `>> mastogone_cron.log 2>&1` to append all output (including errors) to a log file.
- You can also use a virtual environment by activating it in the cron command:

```cron
30 2 * * * cd /path/to/Mastogone && \
  source venv/bin/activate && \
  MASTOGONE_TOKEN=your_token_here \
  python3 mastogone.py --api-base-url https://mastodon.social --no-preview --days 180 --quiet >> mastogone_cron.log 2>&1
```

### 3. Tips
- Always use the `--no-preview` flag in automation to actually delete posts.
- Use `--quiet` for less noise in logs.
- Rotate or clean up your log files periodically.
- Test your command manually before adding it to cron. 

### Example: Delete posts older than 6 months (for cron job)

```zsh
python3 mastogone.py --api-base-url https://mastodon.social --no-preview --days 180 --quiet
```

### Example: Delete posts after a certain date, including replies, with backup

```zsh
python3 mastogone.py --api-base-url https://mastodon.social --no-preview --after 2024-01-01 --include-replies --backup-file backup.jsonl
```

## Security

- Use a Mastodon access token, not your main password.
- Consider using environment variables or a secrets manager for automation.
- Log and backup files are created with restrictive permissions (0600) so only your user can read/write them.
- Never share your access token or include it in logs, backups, or bug reports.

## License

MIT 