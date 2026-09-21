"""Typer entry point. The only user-facing surface."""

from pathlib import Path

import typer

app = typer.Typer(help="Collection, deck, and price tooling.")
ingest_app = typer.Typer(help="Load external data.")
analyze_app = typer.Typer(help="Questions about a decklist.")
export_app = typer.Typer(help="Render to the vault.")
prices_app = typer.Typer(help="Price snapshots.")
app.add_typer(ingest_app, name="ingest")
app.add_typer(analyze_app, name="analyze")
app.add_typer(export_app, name="export")
app.add_typer(prices_app, name="prices")


@ingest_app.command("scryfall")
def ingest_scryfall(force: bool = False) -> None:
    """Download and load the Scryfall default-cards bulk file."""
    raise NotImplementedError


@ingest_app.command("manabox")
def ingest_manabox(csv_path: Path) -> None:
    """Load a ManaBox collection export (utf-8-sig, Name + Quantity)."""
    raise NotImplementedError


@ingest_app.command("precon")
def ingest_precon(code: str) -> None:
    """Load a precon's contents. Not present in collection exports."""
    raise NotImplementedError


@app.command("own")
def own(decklist: Path) -> None:
    """Have / need for a decklist against real inventory."""
    raise NotImplementedError


@analyze_app.command("mana")
def analyze_mana(decklist: Path) -> None:
    """Color demand vs. supply, curve, land count."""
    raise NotImplementedError


@analyze_app.command("legality")
def analyze_legality(decklist: Path, fmt: str) -> None:
    """Format legality and playset eligibility."""
    raise NotImplementedError


@prices_app.command("refresh")
def prices_refresh(vault: Path) -> None:
    """Append a dated snapshot to _log/prices.md."""
    raise NotImplementedError


@export_app.command("obsidian")
def export_obsidian(vault: Path) -> None:
    """Regenerate _generated/ wholesale. Never touches authored notes."""
    raise NotImplementedError


if __name__ == "__main__":
    app()
