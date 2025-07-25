import os
import sys
import logging
import getpass
import re
import json
from datetime import datetime, timedelta, timezone
import time

import click
from tqdm import tqdm
from dateutil import parser
from mastodon import Mastodon, MastodonError

__version__ = "0.1.0"

# ─── Logging Setup ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ─── Security Checks ─────────────────────────────────────────────────────────────
if os.geteuid() == 0:
    logger.warning("It is not recommended to run this script as root.")

# ─── Core Logic ────────────────────────────────────────────────────────────────
def fetch_statuses_page(mastodon, account_id, max_id, limit):
    return mastodon.account_statuses(account_id, max_id=max_id, limit=limit)

def delete_status(mastodon, status_id):
    return mastodon.status_delete(status_id)

def process_statuses(
    api_base_url, access_token, days_old, preview_only, log_file,
    match_patterns=None, use_regex=False, after=None, before=None, backup_file=None,
    include_replies=False, include_reblogs=False,
    quiet=False,
    delete_batch_size=30
):
    mastodon = Mastodon(
        access_token=access_token,
        api_base_url=api_base_url
    )
    try:
        me = mastodon.account_verify_credentials()
        account_id = me['id']
    except Exception as e:
        logger.error("Login failed: %s", e)
        return {"scanned": 0, "matched": 0, "deleted": 0, "failed": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)

    # Parse after/before if provided
    after_dt = parser.parse(after).astimezone(timezone.utc) if after else None
    before_dt = parser.parse(before).astimezone(timezone.utc) if before else None

    statuses = []
    max_id = None

    # Prepare matchers
    compiled_patterns = []
    if match_patterns:
        if use_regex:
            compiled_patterns = [re.compile(p, re.IGNORECASE) for p in match_patterns]
        else:
            compiled_patterns = match_patterns

    if not quiet:
        logger.info(f"Scanning statuses older than {days_old} days…")

    page_bar_args = {"desc": "Fetching pages", "unit": "page"}

    with tqdm(**page_bar_args) as page_bar:
        while True:
            logger.debug(f"Fetching page with max_id={max_id}")
            page = fetch_statuses_page(mastodon, account_id, max_id, limit=40)
            logger.debug(f"Fetched page type: {type(page)}, value: {page!r}")
            if not isinstance(page, list):
                logger.error(f"Expected a list from fetch_statuses_page, got {type(page)}: {page!r}")
                break
            if len(page) == 0:
                logger.debug("No more pages to fetch.")
                break
            logger.debug(f"Fetched {len(page)} statuses on this page.")
            for status in page:
                logger.debug(f"Status type: {type(status)}, value: {status!r}")
                created_at_raw = status['created_at']
                if isinstance(created_at_raw, datetime):
                    created_at = created_at_raw.astimezone(timezone.utc)
                else:
                    created_at = parser.isoparse(created_at_raw).astimezone(timezone.utc)
                text = status.get('content', '')
                # Remove HTML tags from content
                text = re.sub('<[^<]+?>', '', text)
                logger.debug(f"Processing status ID: {status['id']} created at {created_at}")
                # Filter by cutoff, date range, and match patterns
                if created_at < cutoff:
                    is_reply = status['in_reply_to_id'] is not None
                    is_reblog = status['reblog'] is not None
                    if (is_reply and not include_replies) or (is_reblog and not include_reblogs):
                        logger.debug(f"Skipping status ID {status['id']} (reply: {is_reply}, reblog: {is_reblog})")
                        continue
                    in_range = True
                    if after_dt and created_at < after_dt:
                        in_range = False
                    if before_dt and created_at > before_dt:
                        in_range = False
                    matched = True
                    if compiled_patterns:
                        if use_regex:
                            matched = any(p.search(text) for p in compiled_patterns)
                        else:
                            matched = any(p.lower() in text.lower() for p in compiled_patterns)
                    if in_range and matched:
                        logger.debug(f"Status ID {status['id']} matched filters and will be added to delete/preview list.")
                        statuses.append((status['id'], status, created_at))
            if len(page) > 0:
                max_id = page[-1]['id']
            else:
                break
            page_bar.update()

    total = len(statuses)
    logger.info(f"Total statuses matched for processing: {total}")
    logger.debug(f"Statuses variable type before tqdm: {type(statuses)}, value: {statuses!r}")
    if not total:
        logger.info("✅ No statuses to delete/preview.")
        return {"scanned": page_bar.n * 40, "matched": 0, "deleted": 0, "failed": 0}

    if not isinstance(statuses, list):
        logger.error(f"Expected statuses to be a list, got {type(statuses)}: {statuses!r}")
        return {"scanned": page_bar.n * 40, "matched": 0, "deleted": 0, "failed": 0}

    if not log_file:
        log_file = "preview_log.txt" if preview_only else "deleted_statuses_log.txt"
    logger.info(f"Writing details to {log_file}")

    if not backup_file:
        backup_file = "deleted_statuses_backup.jsonl"

    deleted = failed = 0
    backup_fh = None
    try:
        if not preview_only:
            backup_fd = os.open(backup_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            backup_fh = os.fdopen(backup_fd, "a", encoding="utf-8")
        post_bar_args = {"desc": "Processing statuses", "unit": "status"}
        log_fd = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(log_fd, "a", encoding="utf-8") as f, \
             tqdm(statuses, **post_bar_args) as post_bar:
            for status_id, status, created_at in post_bar:
                text = status.get('content', '')
                text = re.sub('<[^<]+?>', '', text)
                text = text.replace("\n", " ")
                logger.debug(f"Writing status ID {status_id} to log and backup.")
                f.write(f"{created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC  {text}\n---\n")
                if not preview_only:
                    backup_fh.write(json.dumps({
                        "id": status_id,
                        "datetime": created_at.isoformat(),
                        "status": convert_datetimes(status)
                    }, ensure_ascii=False) + "\n")
                    try:
                        logger.debug(f"Attempting to delete status ID {status_id}.")
                        delete_status(mastodon, status_id)
                        deleted += 1
                        logger.info(f"Deleted status ID {status_id}.")
                        # Mastodon rate limit: configurable batch size
                        if deleted % delete_batch_size == 0:
                            logger.warning(f"Hit Mastodon delete rate limit ({delete_batch_size} deletes). Pausing for 30 minutes...")
                            time.sleep(1800)
                    except Exception as e:
                        # Handle Mastodon rate limit error (HTTP 429)
                        if hasattr(e, 'response') and getattr(e.response, 'status_code', None) == 429:
                            logger.warning("Received HTTP 429 Too Many Requests. Pausing for 30 minutes due to Mastodon rate limit...")
                            time.sleep(1800)
                            # Retry this status after sleeping
                            try:
                                delete_status(mastodon, status_id)
                                deleted += 1
                                logger.info(f"Deleted status ID {status_id} after rate limit pause.")
                            except Exception as e2:
                                logger.warning(f"Failed deleting {status_id} after rate limit pause: {e2}")
                                failed += 1
                        else:
                            logger.warning(f"Failed deleting {status_id}: {e}")
                            failed += 1
                post_bar.update()
    finally:
        if backup_fh:
            backup_fh.close()

    return {
        "scanned": page_bar.n * 40,
        "matched": total,
        "deleted": deleted,
        "failed": failed
    }

def convert_datetimes(obj):
    if isinstance(obj, dict):
        return {k: convert_datetimes(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_datetimes(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

# ─── CLI ENTRYPOINT ────────────────────────────────────────────────────────────
@click.command(
    help="""
Delete or preview Mastodon posts older than N days.

Features:
- Delete or preview posts by age
- Filter by keyword or regex
- Filter by date range (after/before)
- Optionally include/exclude replies and reblogs
- Backup deleted statuses
- Logging and verbose/quiet modes
- Secure token handling

SECURITY TIP: For automation, consider passing your access token via the MASTOGONE_TOKEN environment variable instead of the --token argument.
"""
)
@click.version_option(__version__, "--version", message="Mastogone version %(version)s")
@click.option("--api-base-url", prompt="Mastodon instance URL", help="Mastodon instance URL (e.g. https://mastodon.social)")
# --token/-p option removed for security
@click.option("--days", "-d", required=False, type=int, help="Delete statuses older than this many days.")
@click.option("--preview/--no-preview", required=False, help="Preview only: show what would be deleted without actually deleting (default: preview)")
@click.option("--log-file", "-l", default=None,
              help="Override log file name (defaults to preview_log.txt or deleted_statuses_log.txt)")
@click.option("--match", "-m", multiple=True, help="Only delete statuses containing this keyword or matching regex (can be used multiple times)")
@click.option("--regex/--no-regex", default=False, help="Interpret --match patterns as regex (default: keyword search)")
@click.option("--after", default=None, help="Only consider statuses after this date (YYYY-MM-DD or ISO format)")
@click.option("--before", default=None, help="Only consider statuses before this date (YYYY-MM-DD or ISO format)")
@click.option("--backup-file", default=None, help="Backup deleted statuses to this JSONL file (default: deleted_statuses_backup.jsonl)")
@click.option("--include-replies/--exclude-replies", default=False, help="Include replies in deletion/preview (default: exclude)")
@click.option("--include-reblogs/--exclude-reblogs", default=False, help="Include reblogs in deletion/preview (default: exclude)")
@click.option("--verbose", is_flag=True, default=False, help="Enable verbose output (DEBUG logging)")
@click.option("--quiet", is_flag=True, default=False, help="Suppress most output except errors")
@click.option("--delete-batch-size", default=30, show_default=True, type=int, help="Number of deletes before pausing for rate limit (default: 30)")
def cli(api_base_url, days, preview, log_file, match, regex, after, before, backup_file, include_replies, include_reblogs, verbose, quiet, delete_batch_size):
    # Check for forbidden --token argument in sys.argv
    for arg in sys.argv:
        if arg.startswith('--token') or arg == '-p':
            logger.error("Passing the token via --token/-p is disabled for security. Use the MASTOGONE_TOKEN environment variable or enter it when prompted.")
            sys.exit(5)

    if quiet:
        logger.setLevel(logging.ERROR)
    elif verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    # Prompt for days if not provided
    if days is None:
        days = click.prompt("Delete statuses older than how many days?", type=int, default=30)
    # Always default preview to True unless explicitly set
    if preview is None:
        preview = True

    token = os.environ.get("MASTOGONE_TOKEN")
    if not token:
        token = getpass.getpass("Access token: ").strip()

    if not token:
        logger.error("No access token provided. Please set the MASTOGONE_TOKEN environment variable or provide it when prompted.")
        sys.exit(4)

    if not preview and days < 1:
        logger.error("Refusing to delete statuses newer than 1 day. Use --days 1 or higher.")
        sys.exit(2)

    logger.info(f"Using instance: {api_base_url}, days: {days}, preview: {preview}")

    try:
        result = process_statuses(
            api_base_url, token, days, True, log_file,  # Always preview first
            match_patterns=match, use_regex=regex,
            after=after, before=before,
            backup_file=backup_file,
            include_replies=include_replies,
            include_reblogs=include_reblogs,
            quiet=quiet
        )
    except (OSError, IOError) as e:
        logger.error(f"File error: {e}")
        sys.exit(3)
    except Exception as e:
        import traceback
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
        sys.exit(99)

    click.echo("\n── Summary ──────────────────────────")
    click.echo(f" Statuses scanned   : {result['scanned']}")
    click.echo(f" Statuses matched   : {result['matched']}")
    click.echo(f" Log file           : {log_file or 'preview_log.txt'}")
    click.echo("──────────────────────────────────────")

    # If there are matches, ask if the user wants to proceed with deletion
    if result['matched'] > 0:
        if click.confirm("Proceed with deleting these posts and back them up to a .json file?", default=False):
            try:
                delete_result = process_statuses(
                    api_base_url, token, days, False, log_file,
                    match_patterns=match, use_regex=regex,
                    after=after, before=before,
                    backup_file="deleted_statuses_backup.jsonl",  # Always write backup
                    include_replies=include_replies,
                    include_reblogs=include_reblogs,
                    quiet=quiet,
                    delete_batch_size=delete_batch_size
                )
            except (OSError, IOError) as e:
                logger.error(f"File error: {e}")
                sys.exit(3)
            except Exception as e:
                import traceback
                logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
                sys.exit(99)
            click.echo("\n── Deletion Summary ──────────────────────────")
            click.echo(f" Statuses deleted   : {delete_result['deleted']}")
            click.echo(f" Delete failures    : {delete_result['failed']}")
            click.echo(f" Backup file        : deleted_statuses_backup.jsonl")
            click.echo("─────────────────────────────────────────────")
            if delete_result["failed"] > 0:
                sys.exit(1)
        else:
            click.echo("No posts were deleted.")
    else:
        click.echo("No posts matched the criteria.")

if __name__ == "__main__":
    cli() 