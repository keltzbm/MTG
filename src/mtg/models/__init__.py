"""Typed domain models. Pydantic, snake_case, oracle_id-keyed."""

from mtg.models.card import Card, Printing
from mtg.models.collection import CollectionEntry
from mtg.models.deck import Deck, DeckEntry

__all__ = ["Card", "Printing", "Deck", "DeckEntry", "CollectionEntry"]
