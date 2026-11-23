import os
import hmac
import hashlib
import sqlite3
import time
import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

def get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value

DISCORD_WEBHOOK_URL = get_required_env("DISCORD_WEBHOOK_URL")
GITHUB_WEBHOOK_SECRET = get_required_env("GITHUB_WEBHOOK_SECRET")

# Review notifications: one message per PR + review type + reviewer per window.
# The state lives in SQLite so every gunicorn worker process sees the same data.
REVIEW_DEDUP_WINDOW_SECONDS = 5 * 60
REVIEW_DEDUP_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review_dedup.sqlite3")

REVIEW_STYLES = {
    "approved": ("Pull Request Approved", 0x2ecc71, "Approved"),
    "changes_requested": ("Changes Requested", 0xe74c3c, "Changes requested"),
    "commented": ("Pull Request Reviewed", 0x95a5a6, "Commented"),
}

def open_dedup_db():
    # isolation_level=None: no implicit transactions, so BEGIN IMMEDIATE below is the only one.
    con = sqlite3.connect(REVIEW_DEDUP_DB_PATH, timeout=10, isolation_level=None)
    con.execute("CREATE TABLE IF NOT EXISTS sent_reviews (key TEXT PRIMARY KEY, sent_at REAL NOT NULL)")
    return con

def claim_review_notification(key: str) -> bool:
    """Return True if this key may post now, recording the post; False if it was posted within the window."""
    now = time.time()
    con = open_dedup_db()
    try:
        # BEGIN IMMEDIATE takes the write lock up front, so check-then-write can't interleave across workers.
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM sent_reviews WHERE sent_at <= ?", (now - REVIEW_DEDUP_WINDOW_SECONDS,))
        if con.execute("SELECT 1 FROM sent_reviews WHERE key = ?", (key,)).fetchone():
            con.execute("COMMIT")
            return False
        con.execute("INSERT INTO sent_reviews (key, sent_at) VALUES (?, ?)", (key, now))
        con.execute("COMMIT")
        return True
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()

@app.route("/webhook", methods=["POST"])
def webhook():
    # Verify GitHub signature for security
    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        print("Missing signature header")
        return "Missing signature", 401
        
    payload = request.get_data()
    expected_signature = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        print(f"Signature mismatch! Expected: {expected_signature}, Got: {signature_header}")
        return "Invalid signature", 401

    event_type = request.headers.get("X-GitHub-Event")
    print(f"Received GitHub event: {event_type}")
    if event_type not in ("pull_request", "pull_request_review"):
        return "", 200

    event = request.get_json(force=True, silent=True)
    if not event:
        print("Failed to parse JSON payload")
        return "", 400

    if event_type == "pull_request_review":
        return handle_review(event)

    action = event.get("action")
    print(f"Pull Request Action: {action}")
    
    valid_actions = ["opened", "synchronize", "closed"]
    if action not in valid_actions:
        return "", 200
    
    pr = event.get("pull_request", {})
    if not pr:
        print("Missing 'pull_request' object in payload")
        return "", 400
        
    is_merged = pr.get("merged", False)
    if action == "closed" and not is_merged:
        print("PR closed but not merged. Ignoring.")
        return "", 200
        
    mergeable = pr.get("mergeable")
    has_conflicts = mergeable is False
    
    change_count = pr.get("changed_files", 0)
    
    mapped_event = action
    if action == "closed" and is_merged:
        mapped_event = "merged"

    send_discord_message(pr, change_count, has_conflicts, mapped_event)
    
    return "", 200

def send_discord_message(pr, change_count, has_conflicts, event_type):
    if event_type == "merged":
        title_prefix = "Pull Request Completed"
        color = 0x9b59b6
        update_reason = "Pull request merged."
    elif event_type == "synchronize":
        title_prefix = "Pull Request Updated"
        color = 0x3498db
        update_reason = "New commits were pushed."
    else:
        title_prefix = "New Pull Request"
        color = 0xf1c40f
        update_reason = "Pull request opened."

    fields = [
        {
            "name": "Event Details",
            "value": update_reason,
            "inline": False
        },
        {
            "name": "Author",
            "value": pr.get("user", {}).get("login", "Unknown"),
            "inline": True
        },
        {
            "name": "From branch",
            "value": pr.get("head", {}).get("ref", ""),
            "inline": True
        },
        {
            "name": "Into branch",
            "value": pr.get("base", {}).get("ref", ""),
            "inline": True
        },
        {
            "name": "Files changed",
            "value": f"{change_count} file(s)",
            "inline": True
        },
        {
            "name": "Merge conflicts",
            "value": "We got conflicts!!!" if has_conflicts else "All good!",
            "inline": True
        },
    ] 

    pr_title = pr.get("title", "Unknown Title")
    pr_url = pr.get("html_url", "")
    
    embed = {
        "title": f"{title_prefix}: {pr_title}",
        "url": pr_url,
        "color": color,
        "fields": fields,
        "timestamp": pr.get("created_at"),
    }

    print("Sending message to Discord...")
    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    if not resp.ok:
        print(f"Failed to send Discord message: {resp.status_code} {resp.text}")
    else:
        print("Successfully sent message to Discord!")

def handle_review(event):
    action = event.get("action")
    print(f"Pull Request Review Action: {action}")
    if action != "submitted":
        return "", 200

    review = event.get("review", {})
    pr = event.get("pull_request", {})
    if not review or not pr:
        print("Missing 'review' or 'pull_request' object in payload")
        return "", 400

    state = (review.get("state") or "").lower()
    if state not in REVIEW_STYLES:
        print(f"Review state '{state}' is not notified. Ignoring.")
        return "", 200

    reviewer = review.get("user", {}).get("login", "Unknown")
    repo = event.get("repository", {}).get("full_name", "")
    key = f"{repo}#{pr.get('number')}:{state}:{reviewer}"
    if not claim_review_notification(key):
        print(f"Review notification '{key}' already sent within the window. Ignoring.")
        return "", 200

    send_review_message(pr, review, state, reviewer)
    return "", 200

def send_review_message(pr, review, state, reviewer):
    title_prefix, color, review_label = REVIEW_STYLES[state]

    fields = [
        {
            "name": "Review",
            "value": review_label,
            "inline": True
        },
        {
            "name": "Reviewer",
            "value": reviewer,
            "inline": True
        },
        {
            "name": "Author",
            "value": pr.get("user", {}).get("login", "Unknown"),
            "inline": True
        },
        {
            "name": "From branch",
            "value": pr.get("head", {}).get("ref", ""),
            "inline": True
        },
        {
            "name": "Into branch",
            "value": pr.get("base", {}).get("ref", ""),
            "inline": True
        },
    ]

    # Embed title limit is 256 characters (https://docs.discord.com/developers/resources/message#embed-object-embed-limits).
    title = f"{title_prefix}: {pr.get('title', 'Unknown Title')}"
    embed = {
        "title": title if len(title) <= 256 else title[:255] + "…",
        "url": review.get("html_url") or pr.get("html_url", ""),
        "color": color,
        "fields": fields,
        "timestamp": review.get("submitted_at"),
    }

    print("Sending review message to Discord...")
    resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]})
    if not resp.ok:
        print(f"Failed to send Discord message: {resp.status_code} {resp.text}")
    else:
        print("Successfully sent review message to Discord!")

if __name__ == "__main__":
    app.run(port=3000, debug=True)
