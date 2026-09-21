from dataclasses import dataclass, field

BOARDS = ("commander", "main", "sideboard", "companion")


@dataclass
class DeckEntry:
    name: str                     # as written; display only
    quantity: int
    board: str = "main"           # commander | main | sideboard | companion
    set_code: str | None = None   # a pinned printing, if the list had one
    collector_number: str | None = None
    oracle_id: str | None = None  # filled by resolve()


@dataclass
class Deck:
    slug: str
    entries: list[DeckEntry] = field(default_factory=list)
    meta: dict = field(default_factory=dict)   # note frontmatter

    @property
    def format(self) -> str:
        return str(self.meta.get("format", "commander"))

    def count(self) -> int:
        return sum(e.quantity for e in self.entries)

    def board(self, name: str) -> list[DeckEntry]:
        return [e for e in self.entries if e.board == name]
