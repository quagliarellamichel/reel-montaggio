"""Palette dei reel (assets/palette.json): varianti del brand a rotazione. Cambia l'accento, la base
resta antracite. La prima palette e' quella di default (verde-smeraldo)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import registro

FILE = Path(__file__).resolve().parent / "assets" / "palette.json"
CAMPI = ("nome", "sfondo", "accento", "testo_chip", "hook", "card_fondo", "card_valore", "card_nota",
         "contorno_sub")
_COLORE = re.compile(r"#[0-9a-fA-F]{6}")


def valida(p: dict) -> dict:
    nome = p.get("nome", "?")
    for campo in CAMPI:
        if campo not in p:
            raise ValueError(f"palette {nome}: manca il campo {campo}")
    if len(p["sfondo"]) != 3:
        raise ValueError(f"palette {nome}: sfondo deve avere 3 colori")
    for colore in list(p["sfondo"]) + [p[c] for c in CAMPI[2:]]:
        if not isinstance(colore, str) or not _COLORE.fullmatch(colore):
            raise ValueError(f"palette {nome}: colore non valido {colore!r}")
    return p


def tutte(file: Path = FILE) -> list[dict]:
    return [valida(p) for p in json.loads(Path(file).read_text(encoding="utf-8"))]


def per_nome(nome: str, file: Path = FILE) -> dict:
    ps = tutte(file)
    for p in ps:
        if p["nome"] == nome:
            return p
    raise ValueError(f"Palette {nome!r} inesistente. Valide: {', '.join(p['nome'] for p in ps)}")


def usate(testo_reels: str) -> list[str]:
    """Palette dei reel in reels.md, dal piu' vecchio al piu' recente; le sezioni scritte prima della
    rotazione (senza riga '- palette:') contano come verde-smeraldo: quei reel erano tutti verdi."""
    return [r.palette or "verde-smeraldo" for r in registro.leggi(testo_reels)]


def prossima(usate: list[str], forzata: str | None = None, file: Path = FILE) -> dict:
    """La prima mai usata (ordine di palette.json); se tutte usate, quella usata meno di recente.
    `forzata` (PALETTE dello scenario) vince. Nomi sconosciuti in `usate` sono ignorati."""
    if forzata:
        return per_nome(forzata, file)
    ps = tutte(file)
    for p in ps:
        if p["nome"] not in usate:
            return p
    ultimo_uso = {nome: i for i, nome in enumerate(usate)}
    return min(ps, key=lambda p: ultimo_uso[p["nome"]])


def _luminanza(colore: str) -> float:
    c = [int(colore[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrasto(a: str, b: str) -> float:
    """Rapporto di contrasto WCAG 2.x tra due colori #rrggbb."""
    la, lb = _luminanza(a), _luminanza(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
