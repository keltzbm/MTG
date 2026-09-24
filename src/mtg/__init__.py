"""Personal Magic tooling. See DESIGN.md.

Invariants:
  * oracle_id is the key. Names are resolved to it once, at the edge.
  * Colors are ordered WUBRG, never alphabetically.
  * The vault is a render target; only _generated/ and _log/ are written.
"""

__version__ = "0.4.0.dev0"

WUBRG = ("W", "U", "B", "R", "G")
