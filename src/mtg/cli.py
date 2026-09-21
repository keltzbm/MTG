"""The only user-facing surface. Everything here is a thin wrapper."""

import shutil
from pathlib import Path
from typing import Annotated

import typer

from mtg import config, sync as syncmod, vault
from mtg.export import formats

app = typer.Typer(help="Collection, decks, prices, and the Obsidian vault.", no_args_is_help=True)
ingest_app = typer.Typer(help="Load outside data.", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

DeckRef = Annotated[str, typer.Argument(help="Deck note slug (aesi-lands) or a path to .md/.txt")]


def _catalog():
    from mtg.store.db import DuckCatalog, connect
    return DuckCatalog(connect())


def _setup():
    cfg = config.load()
    cat = _catalog()
    inv = syncmod.inventory(cfg.collection_csv, cfg.precons, cfg.precon_dir, cat)
    return cfg, cat, inv


@app.command()
def init() -> None:
    """Write a default config and show where everything lives."""
    path = config.write_default()
    cfg = config.load()
    typer.echo(f"config     {path}")
    typer.echo(f"vault      {cfg.vault}")
    typer.echo(f"data       {config.data_dir()}")
    typer.echo(f"precons    {', '.join(cfg.precons) or '(none)'}")


@ingest_app.command("scryfall")
def ingest_scryfall(force: bool = typer.Option(False, help="Download even if under a day old")) -> None:
    """Download Scryfall's bulk card data and load it."""
    from mtg.ingest import scryfall
    typer.echo(scryfall.refresh(force=force))


@ingest_app.command("manabox")
def ingest_manabox(csv_path: Path) -> None:
    """Copy a ManaBox collection export into the data folder."""
    dest = config.load().collection_csv
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(csv_path.expanduser(), dest)
    typer.echo(f"collection -> {dest}")


@app.command()
def decks() -> None:
    """List the deck notes the vault holds."""
    cfg = config.load()
    for d in vault.decks(cfg.mtg_dir):
        typer.echo(f"{d.slug:<28} {d.meta.get('format', ''):<10} {d.meta.get('status', ''):<10} {d.count()} cards")


@app.command()
def own(deck: DeckRef, all_cards: bool = typer.Option(False, "--all", help="Show owned cards too")) -> None:
    """Have / need against your real collection and sealed precons."""
    cfg, cat, inv = _setup()
    rep = syncmod.analyse(vault.find(cfg.mtg_dir, deck), inv, cat)
    from mtg.analysis.ownership import BUY, MARK, summary
    for r in rep.rows:
        if all_cards or r.status == BUY:
            need = f"need {r.shortfall}" if r.status == BUY else ""
            typer.echo(f"{MARK[r.status]} {r.name:<40} {need}")
    s = summary(rep.rows)
    typer.echo(f"\n{s['own']} owned · {s['precon']} in precon boxes · {s['buy']} to buy")
    if rep.unresolved:
        typer.echo(f"unmatched: {', '.join(rep.unresolved)}", err=True)


@app.command()
def price(deck: DeckRef, budget_tix: float = typer.Option(None, help="Compare the MTGO total to a tix budget")) -> None:
    """Paper cost to finish the deck, and MTGO cost for the whole list."""
    cfg, cat, inv = _setup()
    rep = syncmod.analyse(vault.find(cfg.mtg_dir, deck), inv, cat)
    dp = rep.price
    typer.echo(f"paper, whole deck    ${dp.usd_total:,.2f}")
    typer.echo(f"paper, still to buy  ${dp.usd_to_buy:,.2f}")
    typer.echo(f"MTGO, whole deck     {dp.tix_total:,.2f} tix")
    if budget_tix is not None:
        verdict = "fits" if dp.tix_total <= budget_tix else "over by"
        extra = "" if dp.tix_total <= budget_tix else f" {dp.tix_total - budget_tix:,.2f}"
        typer.echo(f"  {verdict}{extra} a {budget_tix:,.0f}-tix budget")
    if dp.missing_on_mtgo:
        typer.echo(f"not on MTGO: {', '.join(dp.missing_on_mtgo)}")


@app.command("export")
def export_deck(
    deck: DeckRef,
    to: str = typer.Option("moxfield", help="moxfield | manabox | mtgo | tcgplayer"),
    pin: str = typer.Option("none", help="none | owned — pin printings you own"),
    out: Path = typer.Option(None, "-o", "--out", help="Write to a file instead of stdout"),
) -> None:
    """Write a deck from the vault in a format another app imports."""
    if to not in formats.FORMATS:
        raise typer.BadParameter(f"--to must be one of {', '.join(formats.FORMATS)}")
    cfg, cat, inv = _setup()
    rep = syncmod.analyse(vault.find(cfg.mtg_dir, deck), inv, cat)
    pins = formats.owned_printings(inv.holdings) if pin == "owned" else {}
    text = formats.render(to, rep.deck, rep.rows, cat, pins)
    if out:
        out.expanduser().write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text, nl=False)
    if rep.unresolved:
        typer.echo(f"unmatched (left as written): {', '.join(rep.unresolved)}", err=True)


@app.command("sync")
def sync_cmd(offline: bool = typer.Option(False, help="Skip the Scryfall refresh")) -> None:
    """Refresh prices, then rewrite the vault's _generated/ and append to _log/."""
    if not offline:
        from mtg.ingest import scryfall
        typer.echo(scryfall.refresh())
    cfg, cat, inv = _setup()
    if not cfg.collection_csv.exists():
        typer.echo("no collection yet — run: mtg ingest manabox <export.csv>", err=True)
    res = syncmod.run(cfg.mtg_dir, inv, cat)
    typer.echo(f"{len(res.decks)} decks · {res.changed_notes} notes updated · "
               f"{res.prices_logged} prices logged · versions changed: {', '.join(res.versions) or 'none'}")
    for w in res.warnings:
        typer.echo(f"  ! {w}", err=True)


if __name__ == "__main__":
    app()
