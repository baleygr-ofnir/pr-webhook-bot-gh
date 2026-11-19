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
   - **Events**: Let me select individual events -> Check **Pull requests** and **Pull request reviews**
   - **Active**: Check
   - Save the webhook.

The bot will now verify the signature of the incoming requests and notify your Discord channel whenever a Pull Request is opened, updated (synchronized), or merged!

It also posts submitted reviews, coloured by type: green for **Approve**, red for **Request changes** and grey for **Comment**. To avoid spam, the same reviewer giving the same type of review on the same PR within 5 minutes is posted only once; repeats in that window are dropped. This state is kept in a SQLite file inside the container (shared by all gunicorn workers) and resets when the container is recreated.

## Deployment

Every push to `main` runs the `Publish image` workflow (`.github/workflows/publish-image.yaml`). It builds a `linux/amd64` image and pushes it to `ghcr.io/baleygr-ofnir/pr-webhook-bot-gh` with two tags:

- `latest`: the rolling tag Komodo watches.
- `sha-<short commit>`: a fixed tag per commit, for rolling back.

The package is private. Komodo picks up new images like this:

1. In Komodo, **Settings > Providers**, add a docker registry account for `ghcr.io` with your GitHub username and a personal access token (classic) with the `read:packages` scope. GitHub Packages only accepts classic tokens.
2. Create a Stack from this repo's `compose.yaml` and attach that registry account, with the `.env` values set on the Stack.
3. Turn on **Auto Update** on the Stack. Komodo then redeploys when the `latest` digest on ghcr.io changes.
4. Komodo checks for new images on the schedule of its **Global Auto Update** Procedure, which new installs run daily at 03:00. Change that schedule if you want redeploys sooner.

To roll back, change the image tag in the Stack's compose file to an older `sha-<short commit>` tag and redeploy. Auto Update has nothing newer to find on a fixed tag, so switch back to `latest` to resume automatic updates.
