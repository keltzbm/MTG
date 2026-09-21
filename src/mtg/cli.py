"""The only user-facing surface. Everything here is a thin wrapper."""

import shutil
from pathlib import Path
from typing import Annotated

import os
import subprocess

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
def ingest_scryfall(
    force: bool = typer.Option(False, help="Download even if under a day old"),
    no_sync: bool = typer.Option(False, "--no-sync", help="Don't resync the vault afterwards"),
) -> None:
    """Download Scryfall's bulk card data and load it."""
    from mtg.ingest import scryfall
    typer.echo(scryfall.refresh(force=force))
    if not no_sync:
        _run_sync(offline=True)


def _copy_manabox(src: Path) -> Path:
    dest = config.load().collection_csv
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src.expanduser(), dest)
    return dest


@ingest_app.command("manabox")
def ingest_manabox(
    csv_path: Path = typer.Argument(None, help="Default: newest ManaBox*.csv in ~/Downloads"),
    no_sync: bool = typer.Option(False, "--no-sync", help="Don't resync the vault afterwards"),
) -> None:
    """Copy a ManaBox collection export into the data folder."""
    from mtg.ingest import manabox
    src = csv_path or manabox.newest_export(config.load().downloads)
    if src is None:
        raise typer.BadParameter("no ManaBox*.csv in ~/Downloads — pass a path")
    typer.echo(f"{src.name} -> {_copy_manabox(src)}")
    if not no_sync:
        _run_sync(offline=True)


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


SHOW = ("buy", "own", "all")


@app.command()
def own(
    deck: DeckRef,
    show: str = typer.Option("buy", "--show", "-s", help="buy | own | all"),
    all_cards: bool = typer.Option(False, "--all", "-a", help="Same as --show all"),
    on_arena: bool = typer.Option(False, "--arena", help="Check against your Arena collection instead of paper"),
) -> None:
    """What to buy for a deck. Numbers are copies in the deck. -a adds what you own."""
    from mtg.analysis.ownership import BUY, MARK, OWN, summary, wildcards
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
    buy_word = "Craft" if on_arena else "Buy"

    wanted = {"buy": [BUY], "own": [OWN], "all": [BUY, OWN]}[show]
    for status in wanted:
        rows = [r for r in rep.rows if r.status == status]
        if not rows:
            continue
        if len(wanted) > 1:
            typer.secho(f"\n{buy_word if status == BUY else 'Own'} ({len(rows)})", bold=True)
        for r in rows:
            n = r.shortfall if status == BUY else r.needed
            extra = f"  (own {r.owned} of {r.needed})" if status == BUY and r.partial else ""
            typer.echo(f"{MARK[status]} {n:>2}  {r.name}{extra}")

    s = summary(rep.rows)
    typer.echo(f"\n{MARK[OWN]} {s[OWN]} own · {MARK[BUY]} {s[BUY]} {buy_word.lower()}")
    if on_arena:
        wc = wildcards(rep.rows, cat)
        typer.echo("wildcards: " + " · ".join(f"{n} {k}" for k, n in wc.items() if n))
    elif show == "buy" and s[OWN]:
        typer.echo("(-a to list what you own too)")
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


def _run_sync(offline: bool = True) -> None:
    """Everything the data affects: collection pickup, prices, generated notes, logs."""
    from mtg.ingest import manabox
    cfg0 = config.load()
    if not offline:
        from mtg.ingest import scryfall
        typer.echo(scryfall.refresh())
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


@app.command("sync")
def sync_cmd(offline: bool = typer.Option(False, help="Skip the Scryfall refresh")) -> None:
    """Refresh prices, pick up a new ManaBox export, rewrite _generated/, append _log/."""
    _run_sync(offline=offline)


def _watched(cfg: config.Config) -> dict[str, float]:
    """Everything whose change should trigger a resync, with its mtime."""
    from mtg.ingest import manabox
    paths = [p for p in vault.deck_notes(cfg.mtg_dir)]
    paths += [cfg.collection_csv, cfg.arena_list, config.config_path()]
    newest = manabox.newest_export(cfg.downloads)
    if newest:
        paths.append(newest)
    return {str(p): p.stat().st_mtime for p in paths if p.exists()}


@app.command()
def watch(interval: float = typer.Option(5.0, help="Seconds between checks")) -> None:
    """Resync whenever a deck note is saved or a new ManaBox export lands. Ctrl-C to stop."""
    import time
    from datetime import datetime
    cfg = config.load()
    typer.echo(f"watching {cfg.mtg_dir} and ~/Downloads — Ctrl-C to stop")
    _run_sync(offline=True)
    seen = _watched(cfg)
    try:
        while True:
            time.sleep(interval)
            now = _watched(cfg)
            if now != seen:
                changed = sorted(Path(p).name for p in set(now) ^ set(seen) | {p for p in now if seen.get(p) != now[p]})
                typer.echo(f"\n{datetime.now():%H:%M:%S} changed: {', '.join(changed)}")
                _run_sync(offline=True)
                seen = _watched(cfg)
    except KeyboardInterrupt:
        typer.echo("\nstopped")


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key><array><string>{exe}</string><string>sync</string></array>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>{hour}</integer><key>Minute</key><integer>{minute}</integer></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def _launchctl_reload(label: str, plist: Path, load: bool = True) -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{label}"], capture_output=True)
    if load:
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)],
                       check=True, capture_output=True, text=True)


@app.command()
def schedule(at: str = typer.Option("07:00", help="Daily time, HH:MM"), remove: bool = False) -> None:
    """Install (or --remove) a macOS launchd job that runs `mtg sync` daily."""
    import sys
    label = "com.keltzbm.mtg-sync"
    plist = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if remove:
        _launchctl_reload(label, plist, load=False)
        plist.unlink(missing_ok=True)
        typer.echo(f"removed {label}")
        return
    hour, minute = (int(x) for x in at.split(":"))
    exe = Path(sys.argv[0]).resolve()
    log = config.data_dir() / "sync.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(PLIST.format(label=label, exe=exe, hour=hour, minute=minute, log=log))
    try:
        _launchctl_reload(label, plist)
    except subprocess.CalledProcessError as e:
        typer.echo(f"wrote {plist} but launchctl bootstrap failed:\n  {e.stderr.strip()}", err=True)
        raise typer.Exit(1)
    typer.echo(f"loaded {label}: daily at {hour:02d}:{minute:02d}\nlog: {log}")


if __name__ == "__main__":
    app()
