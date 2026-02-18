"""CLI entry point for Kompact."""

import click


@click.group()
def cli():
    """Kompact — Multi-layer context optimization proxy for LLM agents."""
    pass


@cli.command()
@click.option("--port", default=7878, help="Port to listen on")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option(
    "--disable",
    multiple=True,
    help="Disable a transform (e.g. --disable toon --disable log_compressor)",
)
@click.option(
    "--anthropic-base-url",
    default="https://api.anthropic.com",
    help="Upstream Anthropic API URL",
)
@click.option(
    "--openai-base-url",
    default="https://api.openai.com",
    help="Upstream OpenAI API URL",
)
def proxy(
    port: int,
    host: str,
    verbose: bool,
    disable: tuple[str, ...],
    anthropic_base_url: str,
    openai_base_url: str,
):
    """Start the Kompact optimization proxy."""
    import uvicorn

    from kompact.config import KompactConfig
    from kompact.proxy.server import create_app

    config = KompactConfig(
        host=host,
        port=port,
        verbose=verbose,
        anthropic_base_url=anthropic_base_url,
        openai_base_url=openai_base_url,
    )

    # Disable requested transforms
    for name in disable:
        transform_config = getattr(config, name, None)
        if transform_config and hasattr(transform_config, "enabled"):
            transform_config.enabled = False
        else:
            click.echo(f"Warning: Unknown transform '{name}'", err=True)

    app = create_app(config)

    click.echo(f"Kompact proxy starting on {host}:{port}")
    click.echo(f"  Anthropic upstream: {anthropic_base_url}")
    click.echo(f"  OpenAI upstream: {openai_base_url}")
    click.echo(f"  Disabled transforms: {', '.join(disable) or 'none'}")
    click.echo(f"  Dashboard: http://{host}:{port}/dashboard")

    uvicorn.run(app, host=host, port=port, log_level="info" if verbose else "warning")


if __name__ == "__main__":
    cli()
