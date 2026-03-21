"""CLI entry point for Kompact."""

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

import click

PLIST_LABEL = "com.kompact.proxy"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _uv_path() -> str:
    return shutil.which("uv") or "/Users/npow/.local/bin/uv"


def _build_plist(
    port: int,
    host: str,
    anthropic_base_url: str,
    openai_base_url: str,
    verbose: bool,
) -> dict:
    args = [
        _uv_path(), "run", "--project", str(Path(__file__).resolve().parents[2]),
        "kompact", "proxy",
        "--port", str(port),
        "--host", host,
        "--anthropic-base-url", anthropic_base_url,
        "--openai-base-url", openai_base_url,
    ]
    if verbose:
        args.append("--verbose")

    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(Path.home() / ".kompact" / "proxy.log"),
        "StandardErrorPath": str(Path.home() / ".kompact" / "proxy.err"),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        },
    }


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
@click.option("--no-otel", is_flag=True, help="Disable OpenTelemetry tracing and metrics")
def proxy(
    port: int,
    host: str,
    verbose: bool,
    disable: tuple[str, ...],
    anthropic_base_url: str,
    openai_base_url: str,
    no_otel: bool,
):
    """Start the Kompact optimization proxy."""
    import uvicorn

    from kompact.config import KompactConfig
    from kompact.proxy.server import create_app

    if not no_otel:
        try:
            from kompact.metrics.telemetry import init as init_otel

            init_otel()
            click.echo("  OpenTelemetry: enabled (OTLP export)")
        except ImportError:
            click.echo(
                "  OpenTelemetry: disabled (install with: pip install kompact[otel])",
                err=True,
            )

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


@cli.group()
def service():
    """Manage the Kompact launchd service."""
    pass


@service.command()
@click.option("--port", default=7878, help="Port to listen on")
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--anthropic-base-url", default="https://api.anthropic.com")
@click.option("--openai-base-url", default="https://api.openai.com")
def install(port: int, host: str, verbose: bool, anthropic_base_url: str, openai_base_url: str):
    """Install and start the Kompact launchd service."""
    log_dir = Path.home() / ".kompact"
    log_dir.mkdir(exist_ok=True)

    plist = _build_plist(port, host, anthropic_base_url, openai_base_url, verbose)

    # Unload existing if present
    if PLIST_PATH.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)

    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    click.echo(f"Installed and started {PLIST_LABEL}")
    click.echo(f"  Listening on {host}:{port}")
    click.echo(f"  Logs: {log_dir / 'proxy.log'}")
    click.echo(f"  Errors: {log_dir / 'proxy.err'}")


@service.command()
def uninstall():
    """Stop and remove the Kompact launchd service."""
    if not PLIST_PATH.exists():
        click.echo("Service not installed.")
        return
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=True)
    PLIST_PATH.unlink()
    click.echo(f"Uninstalled {PLIST_LABEL}")


@service.command()
def restart():
    """Restart the Kompact launchd service."""
    if not PLIST_PATH.exists():
        click.echo("Service not installed. Run 'kompact service install' first.")
        sys.exit(1)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    click.echo(f"Restarted {PLIST_LABEL}")


@service.command()
def status():
    """Show the status of the Kompact launchd service."""
    if not PLIST_PATH.exists():
        click.echo("Service not installed.")
        return
    result = subprocess.run(
        ["launchctl", "list", PLIST_LABEL], capture_output=True, text=True,
    )
    if result.returncode == 0:
        click.echo(f"Service {PLIST_LABEL} is loaded:")
        click.echo(result.stdout)
    else:
        click.echo("Service is installed but not currently loaded.")


if __name__ == "__main__":
    cli()
