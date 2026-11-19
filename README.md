# GitHub PR Webhook to Discord Bot

A simple Flask bot that receives GitHub pull request webhooks and forwards formatted messages to a Discord channel via a Discord webhook.

## Setup

1. Copy `.env.example` to `.env` or just create a `.env` file and set the environment variables:
   ```env
   DISCORD_WEBHOOK_URL=your_discord_webhook_url
   GITHUB_WEBHOOK_SECRET=your_generated_secret_string
   ```

2. Run with Docker Compose:
   ```bash
   docker compose up -d
   ```

3. In your GitHub repository settings, add a new Webhook:
   - **Payload URL**: The URL where your bot is hosted (e.g. `https://your-domain.com/webhook`)
   - **Content type**: `application/json`
   - **Secret**: The same secret string you put in `GITHUB_WEBHOOK_SECRET`
   - **Events**: Let me select individual events -> Check **Pull requests** and **Pull request reviews**
   - **Active**: Check
   - Save the webhook.

The bot will now verify the signature of the incoming requests and notify your Discord channel whenever a Pull Request is opened, updated (synchronized), or merged!

It also posts submitted reviews, coloured by type: green for **Approve**, red for **Request changes** and grey for **Comment**. To avoid spam, the same reviewer giving the same type of review on the same PR within 5 minutes is posted only once; repeats in that window are dropped. This state is kept in a SQLite file inside the container (shared by all gunicorn workers) and resets when the container is recreated.
