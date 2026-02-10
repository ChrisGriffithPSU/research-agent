"""Slack Notifier worker.

Sends notifications to Slack with experiment results, metrics, and plots.
Formats messages for mobile and desktop viewing.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.workers.shared.base_worker import BaseWorker, WorkerConfig
from src.workers.shared.message_schemas import NotificationRequest
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.storage.artifact_store import LocalArtifactStore


logger = logging.getLogger(__name__)


class SlackNotifierWorker(BaseWorker):
    """Worker that sends Slack notifications.

    Sends formatted notifications with metrics, regime breakdown,
    and plot images to configured Slack channels.

    Environment Variables:
        SLACK_WEBHOOK_URL: Slack webhook URL for posting messages
        SLACK_BOT_TOKEN: Slack bot token (optional, for file uploads)
        SLACK_CHANNEL: Target channel (e.g., "#research-alerts")

    Example:
        consumer = MessageConsumer(connection)
        publisher = MessagePublisher(connection)

        worker = SlackNotifierWorker(consumer, publisher)
        await worker.start()
    """

    def __init__(
        self,
        message_consumer: MessageConsumer,
        message_publisher: MessagePublisher,
        artifact_store: Optional[LocalArtifactStore] = None,
        config: Optional[WorkerConfig] = None,
        webhook_url: Optional[str] = None,
        bot_token: Optional[str] = None,
        channel: Optional[str] = None,
    ):
        """Initialize Slack notifier worker.

        Args:
            message_consumer: Message consumer for input queue
            message_publisher: Publisher (not used, but required by base)
            artifact_store: Artifact storage for retrieving plots
            config: Worker configuration
            webhook_url: Slack webhook URL (reads from env if not provided)
            bot_token: Slack bot token (reads from env if not provided)
            channel: Target channel (reads from env if not provided)
        """
        config = config or WorkerConfig(
            queue_name="notify.send",
            dlq_name="notify.dlq",
            max_retries=3,
        )

        super().__init__(
            config=config,
            message_consumer=message_consumer,
            message_publisher=message_publisher,
            artifact_store=artifact_store,
        )

        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel or os.getenv("SLACK_CHANNEL", "#research-alerts")

        if not self.webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not set - notifications will be logged only")

    def get_message_type(self):
        """Get expected message type."""
        return NotificationRequest

    async def process(self, message: NotificationRequest) -> None:
        """Process a notification request.

        Args:
            message: Notification request with content
        """
        logger.info(f"Sending notification: {message.title}")

        # Format message for Slack
        slack_message = self._format_message(message)

        # Send to Slack
        if self.webhook_url:
            await self._send_to_slack(slack_message)
        else:
            # Log message if no webhook configured
            logger.info(f"[SLACK] {json.dumps(slack_message, indent=2)}")

        # Upload plots if available
        if message.plots and self.bot_token:
            for plot_path in message.plots:
                await self._upload_plot(plot_path, message.title)

    def _format_message(self, message: NotificationRequest) -> Dict[str, Any]:
        """Format notification for Slack.

        Args:
            message: Notification request

        Returns:
            Slack message payload
        """
        # Status emoji
        status_emoji = {
            "SUCCESS": ":white_check_mark:",
            "FAILED": ":x:",
            "NEEDS_HUMAN": ":warning:",
            "INFO": ":information_source:",
        }.get(message.status, ":grey_question:")

        # Build message text
        text = f"{status_emoji} *{message.title}*"

        if message.experiment_id:
            text += f"\nExperiment: `{message.experiment_id}`"

        if message.paper_id:
            text += f"\nPaper: `{message.paper_id}`"

        text += f"\n\n{message.message}"

        # Add metrics if present
        if message.metrics:
            text += "\n\n*Metrics:*"
            for key, value in message.metrics.items():
                text += f"\n• {key}: {value}"

        # Add regime breakdown if present
        if message.regime_breakdown:
            text += "\n\n*Regime Breakdown:*"
            for regime in message.regime_breakdown[:5]:  # Limit to 5 regimes
                regime_name = regime.get("regime_name", "Unknown")
                regime_metrics = regime.get("metrics", {})
                text += f"\n• {regime_name}:"
                for k, v in list(regime_metrics.items())[:3]:  # Limit metrics
                    text += f" {k}={v}"

        # Add recommendation
        if message.recommendation:
            rec_emoji = {
                "PROMOTE": ":rocket:",
                "KILL": ":wastebasket:",
                "INVESTIGATE": ":mag:",
            }.get(message.recommendation, "")
            text += f"\n\n{rec_emoji} *Recommendation: {message.recommendation}*"

        # Add artifact links
        if message.artifact_refs:
            text += "\n\n*Artifacts:*"
            for ref in message.artifact_refs[:3]:  # Limit links
                text += f"\n• {ref}"

        # Build blocks for rich formatting
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": message.title,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            },
        ]

        # Add metrics as fields if present
        if message.metrics:
            fields = []
            for key, value in list(message.metrics.items())[:10]:  # Max 10 fields
                fields.append(
                    {
                        "type": "mrkdwn",
                        "text": f"*{key}:*\n{value}",
                    }
                )

            if fields:
                blocks.append(
                    {
                        "type": "section",
                        "fields": fields,
                    }
                )

        # Add divider
        blocks.append({"type": "divider"})

        return {
            "text": text,  # Fallback text
            "blocks": blocks,
            "channel": self.channel,
        }

    async def _send_to_slack(self, message: Dict[str, Any]) -> None:
        """Send message to Slack webhook.

        Args:
            message: Slack message payload
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=message,
                    timeout=30.0,
                )
                response.raise_for_status()
                logger.debug("Slack notification sent successfully")

        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
            raise

    async def _upload_plot(self, plot_path: str, title: str) -> None:
        """Upload plot image to Slack.

        Args:
            plot_path: Path to plot image
            title: Upload title
        """
        if not self.bot_token:
            return

        try:
            import httpx

            # Read plot file
            if plot_path.startswith("/"):
                full_path = plot_path
            else:
                # Assume relative to artifacts base
                full_path = str(Path(os.getenv("ARTIFACTS_BASE_DIR", "./artifacts")) / plot_path)

            with open(full_path, "rb") as f:
                plot_data = f.read()

            # Upload to Slack
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/files.upload",
                    headers={"Authorization": f"Bearer {self.bot_token}"},
                    data={
                        "channels": self.channel,
                        "title": title,
                    },
                    files={"file": (Path(plot_path).name, plot_data, "image/png")},
                    timeout=60.0,
                )

                result = response.json()
                if not result.get("ok"):
                    logger.error(f"Slack upload failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"Failed to upload plot {plot_path}: {e}")

    async def health_check(self) -> bool:
        """Check worker health."""
        if not self.webhook_url:
            return True  # No webhook configured is not a failure

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                # Slack webhooks return 400 on GET, which is fine for health check
                response = await client.get(self.webhook_url, timeout=5.0)
                # Any response means the endpoint is reachable
                return response.status_code in [400, 200, 301, 302]

        except Exception:
            return False
