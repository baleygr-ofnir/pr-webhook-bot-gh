# GitHub PR Webhook to Discord Bot

A simple Flask bot that receives GitHub pull request webhooks and forwards formatted messages to a Discord channel via a Discord webhook.

## Setup

1. Copy `.env.example` to `.env` or just create a `.env` file and set the environment variables:
   ```env
   DISCORD_WEBHOOK_URL=your_discord_webhook_url
   GITHUB_WEBHOOK_SECRET=your_generated_secret_string
   ```

2. Run with Docker Compose. `compose.yaml` pulls the published image `ghcr.io/baleygr-ofnir/pr-webhook-bot-gh:latest`, which is private, so sign in to ghcr.io first with a personal access token (classic) that has the `read:packages` scope:
   ```bash
   echo $CR_PAT | docker login ghcr.io -u <your-github-username> --password-stdin
   docker compose up -d
   ```
   To run local changes instead, build the image yourself: `docker build -t ghcr.io/baleygr-ofnir/pr-webhook-bot-gh:latest .` before `docker compose up -d`.

3. In your GitHub repository settings, add a new Webhook:
   - **Payload URL**: The URL where your bot is hosted (e.g. `https://your-domain.com/webhook`)
   - **Content type**: `application/json`
   - **Secret**: The same secret string you put in `GITHUB_WEBHOOK_SECRET`
   - **Events**: Let me select individual events -> Check **Pull requests**, **Pull request reviews**, **Issue comments** and **Pull request review comments**
   - **Active**: Check
   - Save the webhook.

The bot will now verify the signature of the incoming requests and notify your Discord channel whenever a Pull Request is opened, updated (synchronized), or merged!

It also posts submitted reviews, coloured by type: green for **Approve**, red for **Request changes** and grey for **Comment**. To avoid spam, the same reviewer giving the same type of review on the same PR within 5 minutes is posted only once; repeats in that window are dropped. This state is kept in a SQLite file inside the container (shared by all gunicorn workers) and resets when the container is recreated.

Comments on a PR post the same grey **Comment** card: comments in the Conversation tab (also `gh pr comment`) and single comments on diff lines. Conversation comments carry no branch data, so their From and Into branch fields show `—`. Line comments that belong to a submitted review add no card of their own; the review's card covers them. Comments are filtered separately from reviews: the same person commenting on the same PR within 5 minutes is posted once. Comments on plain issues are ignored.

## Deployment

Every push to `main` runs the `Publish image` workflow (`.github/workflows/publish-image.yaml`). It builds a `linux/amd64` image and pushes it to `ghcr.io/baleygr-ofnir/pr-webhook-bot-gh` with two tags:

- `latest`: the rolling tag Komodo watches.
- `sha-<short commit>`: a fixed tag per commit, for rolling back.

The package is private, so Komodo needs credentials to pull it.

### 1. Create a GitHub token for pulling

GitHub Packages only accepts a personal access token (classic), not a fine-grained token.

1. On GitHub, click your profile picture, then **Settings**.
2. In the left sidebar, click **Developer settings**, then under **Personal access tokens** click **Tokens (classic)**.
3. Click **Generate new token**, then **Generate new token (classic)**.
4. In **Note**, give it a name such as `komodo ghcr pull`, and pick an **Expiration**. When it expires, Komodo can no longer pull, so note the date.
5. Select only the **`read:packages`** scope. Leave `repo` unticked: pulling doesn't need it.
6. Click **Generate token** and copy the token.

### 2. Add ghcr.io as a registry provider in Komodo

1. In Komodo, go to **Settings > Providers**.
2. Add a new **docker registry** account:
   - **Domain**: `ghcr.io`
   - **Username**: your GitHub username
   - **Token**: the token from step 1

Accounts added in the UI are stored in Komodo's database and can be edited or deleted there. Alternatively, put the account in `core.config.toml` (available to every server) or a server's `periphery.config.toml` (only that server):

```toml
[[image_registry]]
domain = "ghcr.io"
accounts = [
  { username = "<your-github-username>", token = "<token>" },
]
```

Tokens from config files show up in the UI but can't be read back there.

### 3. Create the Stack

1. Create a Stack on the server that should run the bot, using this repo's `compose.yaml`.
2. In the Stack's config, set the image registry to the `ghcr.io` provider and the account you added. These are the Stack's `registry_provider` and `registry_account` settings; Komodo logs in with them before `docker compose pull` and `up`.
3. Set the `.env` values (`DISCORD_WEBHOOK_URL`, `GITHUB_WEBHOOK_SECRET`, `CONTAINER_PORT`, `GUNICORN_WORKERS`) in the Stack's environment.
4. Turn on **Auto Update**. Komodo then redeploys when the `latest` digest on ghcr.io changes. It implies **Poll for Updates**, so you don't need both.
5. Deploy once by hand to check the login and pull work. If the registry login fails, Komodo stops the deploy and shows the error in the Stack's logs.

Komodo checks for new images on the schedule of its **Global Auto Update** Procedure, which new installs run daily at 03:00. Change that schedule if you want redeploys sooner.

To roll back, change the image tag in the Stack's compose file to an older `sha-<short commit>` tag and redeploy. Auto Update has nothing newer to find on a fixed tag, so switch back to `latest` to resume automatic updates.
