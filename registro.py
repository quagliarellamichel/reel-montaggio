"""Registro dei reel in reels.md: una sezione '## titolo' per reel, campi '- chiave: valore',
caption come blocco citato '  > '. Letto e riscritto dal workflow di pubblicazione."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Reel:
    titolo: str
    stato: str
    video: str
    caption: str
    inizio: int
    fine: int
    palette: str = ""
    youtube: str = ""


def nuova_sezione(titolo: str, video: str, caption: str, palette: str | None = None) -> str:
    quoted = "\n".join(f"  > {r}" if r else "  >" for r in caption.split("\n"))
    riga_palette = f"- palette: {palette}\n" if palette else ""
    return f"## {titolo}\n- stato: in-coda\n- video: {video}\n{riga_palette}- caption:\n{quoted}\n\n"


def leggi(testo: str) -> list[Reel]:
    righe = testo.split("\n")
    inizi = [i for i, r in enumerate(righe) if r.startswith("## ")]
    reels = []
    for n, i in enumerate(inizi):
        fine = inizi[n + 1] if n + 1 < len(inizi) else len(righe)
        campi, caption = {}, []
        for r in righe[i + 1:fine]:
            if r.startswith("  >"):
                caption.append(r[4:] if r.startswith("  > ") else "")
            elif r.startswith("- ") and ":" in r:
                k, v = r[2:].split(":", 1)
                campi[k.strip()] = v.strip()
        reels.append(Reel(righe[i][3:].strip(), campi.get("stato", ""), campi.get("video", ""),
                          "\n".join(caption), i, fine, campi.get("palette", ""), campi.get("youtube", "")))
    return reels


def prossimo(reels: list[Reel]) -> Reel | None:
    return next((r for r in reels if r.stato == "in-coda"), None)


def prossimo_youtube(reels: list[Reel]) -> Reel | None:
    """Coda YouTube: il primo già uscito su Instagram e senza riga '- youtube:' (anche 'salta' o
    'errore: …' lo escludono; per ritentare si cancella la riga a mano)."""
    return next((r for r in reels if r.stato == "pubblicato" and not r.youtube), None)


def _riscrivi(testo: str, reel: Reel, stato: str | None, extra: str) -> str:
    # `extra` è sempre "- chiave: valore": il valore può arrivare da fonti non fidate
    # (es. testo di un'eccezione nel fallback permalink) e va sempre appiattito su una
    # riga sola, altrimenti un '\n' o un '## ' dentro spezzerebbe il registro.
    chiave, _, valore = extra.partition(": ")
    extra = f"{chiave}: {' '.join(valore.split())}"
    righe = testo.split("\n")
    sezione = [f"- stato: {stato}" if stato and r.startswith("- stato:") else r for r in righe[reel.inizio:reel.fine]]
    pos = next(i for i, r in enumerate(sezione) if r.startswith("- stato:")) + 1
    sezione.insert(pos, extra)
    return "\n".join(righe[:reel.inizio] + sezione + righe[reel.fine:])


def segna_pubblicato(testo: str, reel: Reel, data: str, permalink: str) -> str:
    return _riscrivi(testo, reel, "pubblicato", f"- pubblicato: {data} · {permalink}")


def segna_errore(testo: str, reel: Reel, motivo: str) -> str:
    return _riscrivi(testo, reel, "errore", f"- errore: {motivo}")


def segna_youtube(testo: str, reel: Reel, valore: str) -> str:
    return _riscrivi(testo, reel, None, f"- youtube: {valore}")
