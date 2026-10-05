# GitHub PR Webhook to Discord Bot

A simple Flask bot that receives GitHub pull request webhooks and forwards formatted messages to a Discord channel via a Discord webhook.

## Setup

1. Copy .env.example to .env or just create a .env file and set the environment variables:
   `nv
   DISCORD_WEBHOOK_URL=your_discord_webhook_url
   GITHUB_WEBHOOK_SECRET=your_generated_secret_string
   `

2. Run with Docker Compose:
   `ash
   docker compose up -d
   `

3. In your GitHub repository settings, add a new Webhook:
   - **Payload URL**: The URL where your bot is hosted (e.g. https://your-domain.com/webhook)
   - **Content type**: pplication/json
   - **Secret**: The same secret string you put in GITHUB_WEBHOOK_SECRET
   - **Events**: Let me select individual events -> Check **Pull requests**
   - **Active**: Check
   - Save the webhook.

The bot will now verify the signature of the incoming requests and notify your Discord channel whenever a Pull Request is opened, updated (synchronized), or merged!
