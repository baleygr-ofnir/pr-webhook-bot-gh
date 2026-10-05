import os
import hmac
import hashlib
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
    if event_type != "pull_request":
        return "", 200
        
    event = request.get_json(force=True, silent=True)
    if not event:
        print("Failed to parse JSON payload")
        return "", 400
        
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
        color = 0x2ecc71
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
    
if __name__ == "__main__":
    app.run(port=3000, debug=True)
