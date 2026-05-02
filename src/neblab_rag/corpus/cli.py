"""CLI entrypoint for corpus ingestion.

Usage::

    neblab-ingest ingest --max 200 --language en
    neblab-ingest ingest --topic desertification --language zh

Registered as console script ``neblab-ingest`` via pyproject.toml.
"""

import click

from neblab_rag.config import get_settings
from neblab_rag.corpus.ingestion import IngestionService
from neblab_rag.corpus.openalex_client import OpenAlexClient
from neblab_rag.corpus.topics import TOPIC_BY_ID, TOPICS
from neblab_rag.db.engine import get_session
from neblab_rag.logging_config import configure_logging, get_logger

log = get_logger(__name__)


@click.group()
def cli() -> None:
    """NEBLab corpus operations."""
    configure_logging(get_settings().log_level)


@cli.command("ingest")
@click.option("--topic", "topic_id", default=None, help="Topic id; default: all topics")
@click.option(
    "--language",
    default="en",
    type=click.Choice(["en", "zh"]),
    help="Language to ingest",
)
@click.option("--max", "max_results", default=500, type=int)
def ingest(topic_id: str | None, language: str, max_results: int) -> None:
    """Ingest OpenAlex metadata for topic(s)."""
    settings = get_settings()
    client = OpenAlexClient(email=settings.openalex_email)

    topics = [TOPIC_BY_ID[topic_id]] if topic_id else TOPICS

    total = 0
    with get_session() as session:
        service = IngestionService(client=client, session=session)
        for t in topics:
            n = service.ingest_topic(t, language=language, max_results=max_results)
            total += n
    log.info("ingest_total", count=total)
    click.echo(f"Ingested {total} documents")


if __name__ == "__main__":
    cli()
