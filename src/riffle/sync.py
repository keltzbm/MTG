"""The work behind `riffle sync`, kept free of the CLI and the database so it's testable."""

from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from riffle import vault
from riffle.analysis import ownership, pricing
from riffle.analysis.resolve import counts, resolve_deck, resolve_holdings
from riffle.export import formats, obsidian
from riffle.ingest import arena, manabox
from riffle.models import Deck, Holding, Prices
from riffle.store import Catalog


@dataclass
class Inventory:
    holdings: list[Holding]
    unresolved: list[str] = field(default_factory=list)

    @cached_property
    def owned(self) -> Counter:
        """Copies owned per card_id. Computed once: holdings are resolved before
        an Inventory is built and never change after."""
        return counts(self.holdings)


def inventory(collection_csv: Path, catalog: Catalog) -> Inventory:
    holdings = manabox.load(collection_csv) if collection_csv.exists() else []
    return Inventory(holdings, resolve_holdings(holdings, catalog))


def arena_inventory(arena_list: Path, catalog: Catalog) -> Inventory:
    holdings = arena.load(arena_list) if arena_list.exists() else []
    return Inventory(holdings, resolve_holdings(holdings, catalog))


@dataclass
class DeckReport:
    deck: Deck
    rows: list[ownership.Row]
    price: pricing.DeckPrice
    unresolved: list[str]


def analyse(deck: Deck, inv: Inventory, catalog: Catalog) -> DeckReport:
    missing = resolve_deck(deck, catalog)
    rows = ownership.diff(deck, inv.owned, catalog)
    return DeckReport(deck, rows, pricing.price(rows, catalog), missing)


@dataclass
class SyncResult:
    decks: list[str] = field(default_factory=list)
    changed_notes: int = 0
    versions: list[str] = field(default_factory=list)
    prices_logged: int = 0
    removed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run(mtg_dir: Path, inv: Inventory, catalog: Catalog, today: str | None = None) -> SyncResult:
    today = today or obsidian.today()
    gen, log = mtg_dir / "_generated", mtg_dir / "_log"
    res = SyncResult()
    pins = formats.owned_printings(inv.holdings)
    keep = {"collection-summary.md"}
    for deck in vault.decks(mtg_dir):
        rep = analyse(deck, inv, catalog)
        res.decks.append(deck.slug)
        imports = {
            "Moxfield import — owned printings pinned": formats.moxfield(deck, catalog, pins),
            "ManaBox import — owned printings pinned": formats.manabox(deck, catalog, pins),
            "MTGO import": formats.mtgo(deck, catalog),
        }
        text = obsidian.deck_data(deck, rep.rows, rep.price, rep.unresolved, today, imports)
        res.changed_notes += obsidian.write_deck(gen, deck, text)
        keep.add(f"{deck.slug}-data.md")
        if obsidian.append_version(log, deck, catalog, today):
            res.versions.append(deck.slug)
        if rep.unresolved:
            res.warnings.append(f"{deck.slug}: unmatched {', '.join(rep.unresolved)}")
    res.changed_notes += obsidian.write_summary(
        gen, obsidian.collection_summary(inv.holdings, catalog, today)
    )
    res.removed = obsidian.prune(gen, keep)
    wanted = []
    for name in vault.buy_cards(mtg_dir.parent):
        card_id = catalog.resolve(name)
        if card_id is None:
            res.warnings.append(f"buy list: unmatched {name}")
        else:
            wanted.append(card_id)
    prices = catalog.prices(wanted)
    buys = []
    for card_id in wanted:
        p = prices.get(card_id, Prices())
        buys.append((catalog.name(card_id), p.usd, p.tix))
    res.prices_logged = obsidian.append_prices(log / "prices.md", buys, today)
    if inv.unresolved:
        res.warnings.append(f"collection: {len(inv.unresolved)} rows unmatched, e.g. {inv.unresolved[:3]}")
    return res
