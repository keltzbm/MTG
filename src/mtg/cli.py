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


def _copy_manabox(src: Path) -> Path:
    dest = config.load().collection_csv
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src.expanduser(), dest)
    return dest


@ingest_app.command("manabox")
def ingest_manabox(csv_path: Path = typer.Argument(None, help="Default: newest ManaBox*.csv in ~/Downloads")) -> None:
    """Copy a ManaBox collection export into the data folder."""
    from mtg.ingest import manabox
    src = csv_path or manabox.newest_export(config.load().downloads)
    if src is None:
        raise typer.BadParameter("no ManaBox*.csv in ~/Downloads — pass a path")
    typer.echo(f"{src.name} -> {_copy_manabox(src)}")


@ingest_app.command("arena")
def ingest_arena(path: Path) -> None:
    """Load an Arena collection export (text list or CSV with name + count)."""
    from mtg.ingest import arena
    holdings = arena.load(path.expanduser())
    dest = config.load().arena_list
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(f"{h.quantity} {h.name}\n" for h in holdings), encoding="utf-8")
    typer.echo(f"{len(holdings)} Arena cards -> {dest}")


@app.command()
def decks() -> None:
    """List the deck notes the vault holds."""
    cfg = config.load()
    for d in vault.decks(cfg.mtg_dir):
        typer.echo(f"{d.slug:<28} {d.meta.get('format', ''):<10} {d.meta.get('status', ''):<10} {d.count()} cards")


SHOW = ("need", "owned", "precon", "all")


@app.command()
def own(
    deck: DeckRef,
    show: str = typer.Option("need", "--show", "-s", help="need | owned | precon | all"),
    all_cards: bool = typer.Option(False, "--all", "-a", help="Same as --show all"),
    on_arena: bool = typer.Option(False, "--arena", help="Check against your Arena collection instead of paper"),
) -> None:
    """Have / need. 🟥 how many to buy · 🟦 covered by a sealed precon · 🟩 how many you own."""
    from mtg.analysis.ownership import BUY, MARK, OWN, PRECON, summary, wildcards
    show = "all" if all_cards else show
    if show not in SHOW:
        raise typer.BadParameter(f"--show must be one of {', '.join(SHOW)}")
    cfg = config.load()
    cat = _catalog()
    if on_arena:
        if not cfg.arena_list.exists():
            raise typer.BadParameter("no Arena collection yet — run: mtg ingest arena <file>")
        inv = syncmod.arena_inventory(cfg.arena_list, cat)
    else:
        inv = syncmod.inventory(cfg.collection_csv, cfg.precons, cfg.precon_dir, cat)
    rep = syncmod.analyse(vault.find(cfg.mtg_dir, deck), inv, cat)

    sections = [
        (BUY, "To buy" if not on_arena else "To craft", lambda r: r.shortfall),
        (PRECON, "In precon boxes", lambda r: r.needed),
        (OWN, "Owned", lambda r: r.owned),
    ]
    wanted = {"need": {BUY}, "owned": {OWN}, "precon": {PRECON}, "all": {BUY, PRECON, OWN}}[show]
    for status, title, number in sections:
        rows = [r for r in rep.rows if r.status == status]
        if status not in wanted or not rows:
            continue
        if len(wanted) > 1:
            typer.secho(f"\n{title} ({len(rows)})", bold=True)
        for r in rows:
            typer.echo(f"{MARK[status]} {number(r):>2}  {r.name}")

    s = summary(rep.rows)
    typer.echo(f"\n{MARK[OWN]} {s[OWN]} owned · {MARK[PRECON]} {s[PRECON]} in precon boxes · {MARK[BUY]} {s[BUY]} to "
               + ("craft" if on_arena else "buy"))
    if on_arena:
        wc = wildcards(rep.rows, cat)
        typer.echo("wildcards: " + " · ".join(f"{n} {k}" for k, n in wc.items() if n))
    elif show == "need" and s[OWN]:
        typer.echo("(--all or -a to list the owned cards too)")
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
    to: str = typer.Option("moxfield", help="moxfield | manabox | mtgo | arena | tcgplayer"),
    pin: str = typer.Option("owned", help="owned | none — pin printings you own"),
    out: Path = typer.Option(None, "-o", "--out", help="File, or a folder when the deck is 'all'"),
) -> None:
    """Write a deck — or every deck, with 'all' — in a format another app imports."""
    if to not in formats.FORMATS:
        raise typer.BadParameter(f"--to must be one of {', '.join(formats.FORMATS)}")
    cfg, cat, inv = _setup()
    pins = formats.owned_printings(inv.holdings) if pin == "owned" else {}
    targets = vault.decks(cfg.mtg_dir) if deck == "all" else [vault.find(cfg.mtg_dir, deck)]
    if deck == "all" and out is None:
        raise typer.BadParameter("exporting all decks needs --out <folder>")
    for d in targets:
        rep = syncmod.analyse(d, inv, cat)
        text = formats.render(to, rep.deck, rep.rows, cat, pins)
        if deck == "all":
            folder = out.expanduser()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{d.slug}-{to}.txt"
            path.write_text(text, encoding="utf-8")
            typer.echo(f"wrote {path}")
        elif out:
            out.expanduser().write_text(text, encoding="utf-8")
            typer.echo(f"wrote {out}")
        else:
            typer.echo(text, nl=False)
        if rep.unresolved:
            typer.echo(f"{d.slug}: unmatched (left as written): {', '.join(rep.unresolved)}", err=True)


@app.command("sync")
def sync_cmd(offline: bool = typer.Option(False, help="Skip the Scryfall refresh")) -> None:
    """Refresh prices, then rewrite the vault's _generated/ and append to _log/."""
    if not offline:
        from mtg.ingest import scryfall
        typer.echo(scryfall.refresh())
    from mtg.ingest import manabox
    cfg0 = config.load()
    newest = manabox.newest_export(cfg0.downloads)
    stored = cfg0.collection_csv
    if newest and (not stored.exists() or newest.stat().st_mtime > stored.stat().st_mtime):
        _copy_manabox(newest)
        typer.echo(f"picked up {newest.name} from Downloads")
    cfg, cat, inv = _setup()
    if not cfg.collection_csv.exists():
        typer.echo("no collection yet — export from ManaBox to ~/Downloads, or: mtg ingest manabox <csv>", err=True)
    res = syncmod.run(cfg.mtg_dir, inv, cat)
    typer.echo(f"{len(res.decks)} decks · {res.changed_notes} notes updated · "
               f"{res.prices_logged} prices logged · versions changed: {', '.join(res.versions) or 'none'}")
    if res.removed:
        typer.echo(f"removed stale generated notes: {', '.join(res.removed)}")
    for w in res.warnings:
        typer.echo(f"  ! {w}", err=True)


if __name__ == "__main__":
    app()
