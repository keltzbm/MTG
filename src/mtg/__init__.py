"""Personal Magic tooling. See DESIGN.md.

Invariants enforced across every module:
  * oracle_id is the key. Never match on name.
  * Colors are ordered WUBRG, never alphabetically.
  * The vault is a render target; this package writes _generated/ and _log/ only.
"""

__version__ = "0.2.0.dev0"

WUBRG = ("W", "U", "B", "R", "G")
