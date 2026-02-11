"""Main entry point for quant research agent.

CLI for running workers, scheduler, and administrative tasks.
"""

import asyncio
import logging
import sys
from typing import Optional, cast

import typer
from rich.console import Console
from rich.logging import RichHandler

from src.shared.llm.openai_client import OpenAIClient
from src.shared.messaging.connection import RabbitMQConnection
from src.shared.messaging.config import messaging_config
from src.shared.messaging.consumer import MessageConsumer
from src.shared.messaging.publisher import MessagePublisher
from src.shared.interfaces import IMessageConnection


app = typer.Typer(help="Quant Research Agent CLI")
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Setup logging configuration.

    Args:
        verbose: Enable debug logging if True
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def scheduler(
    interval: int = typer.Option(30, help="Fetch interval in minutes"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the ArXiv fetcher scheduler."""
    setup_logging(verbose)

    from src.scheduler import ArxivScheduler

    async def run():
        s = ArxivScheduler(interval_minutes=interval)
        try:
            await s.start()
        except KeyboardInterrupt:
            console.print("\n[yellow]Shutting down...[/yellow]")
            await s.stop()

    asyncio.run(run())


@app.command()
def fetch_once(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run ArXiv fetcher once (for testing)."""
    setup_logging(verbose)

    from src.scheduler import ArxivScheduler

    async def run():
        s = ArxivScheduler()
        await s.run_once()

    asyncio.run(run())


@app.command()
def worker(
    name: str = typer.Argument(
        ...,
        help="Worker name: triage, pdf_parser, concept_gen, experiment_exploder, notifier, kimi",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run a specific worker."""
    setup_logging(verbose)

    async def run():
        if name == "kimi":
            from workers.kimi_worker.mq_worker import run_queue_worker

            await run_queue_worker()
            return

        # Setup RabbitMQ connection
        connection = RabbitMQConnection(messaging_config)
        await connection.connect()

        # Create consumer and publisher
        consumer = MessageConsumer(connection)
        publisher = MessagePublisher(cast(IMessageConnection, connection))

        # Create worker based on name
        if name == "triage":
            from src.workers.paper_triage.worker import PaperTriageWorker

            w = PaperTriageWorker(
                llm_client=OpenAIClient(profile="triage"),
                message_consumer=consumer,
                message_publisher=publisher,
            )
        elif name == "pdf_parser":
            try:
                from src.workers.pdf_parser.worker import PDFParserWorker
            except ImportError:
                console.print(
                    "[red]pdf_parser requires the 'arxiv' extra (docling).[\/red]"
                )
                console.print("Install with: uv sync --extra arxiv")
                raise

            w = PDFParserWorker(
                message_consumer=consumer,
                message_publisher=publisher,
            )
        elif name == "concept_gen":
            from src.workers.concept_generator.worker import ConceptGeneratorWorker

            w = ConceptGeneratorWorker(
                llm_client=OpenAIClient(profile="concept_gen"),
                message_consumer=consumer,
                message_publisher=publisher,
            )
        elif name == "experiment_exploder":
            from src.workers.experiment_exploder.worker import ExperimentExploderWorker

            w = ExperimentExploderWorker(
                llm_client=OpenAIClient(profile="experiment_exploder"),
                message_consumer=consumer,
                message_publisher=publisher,
            )
        elif name == "notifier":
            from src.workers.notifier.slack_worker import SlackNotifierWorker

            w = SlackNotifierWorker(
                message_consumer=consumer,
                message_publisher=publisher,
            )
        else:
            console.print(f"[red]Unknown worker: {name}[/red]")
            console.print(
                "Available workers: triage, pdf_parser, concept_gen, experiment_exploder, notifier, kimi"
            )
            sys.exit(1)

        console.print(f"[green]Starting {name} worker...[/green]")

        try:
            await w.start()
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Shutting down {name} worker...[/yellow]")
            await w.stop()
        finally:
            await connection.close()

    asyncio.run(run())


@app.command()
def health_check(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Check health of all components."""
    setup_logging(verbose)

    async def run():
        console.print("[bold]Health Check[/bold]\n")

        # Check LLM
        console.print("Checking LLM...", end=" ")
        try:
            llm = OpenAIClient(profile="triage")
            healthy = await llm.health_check()
            if healthy:
                console.print("[green]OK[/green]")
            else:
                console.print("[red]FAIL[/red]")
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")

        # Check RabbitMQ
        console.print("Checking RabbitMQ...", end=" ")
        try:
            connection = RabbitMQConnection(messaging_config)
            await connection.connect()
            console.print("[green]OK[/green]")
            await connection.close()
        except Exception as e:
            console.print(f"[red]ERROR: {e}[/red]")

        console.print("\n[bold]Health check complete[/bold]")

    asyncio.run(run())


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]Quant Research Agent[/bold]")
    console.print("Version: 0.1.0")
    console.print("Focus: MFT Research (5-30s holding)")


if __name__ == "__main__":
    app()
