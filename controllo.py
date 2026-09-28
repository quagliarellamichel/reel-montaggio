"""Controllo automatico dopo ogni render: foglio fotogrammi + avvisi. Non blocca niente: la
revisione umana prima di pubblicare resta obbligatoria."""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

import timeline
from montaggio import BARRA, BARRA_ORIZZONTALE, FINESTRA, FINESTRA_ORIZZONTALE


def uniforme(pixels: bytes, soglia: float = 4.0) -> bool:
    """Finestra quasi di un solo colore: pagina bianca o in caricamento."""
    if not pixels:
        return False
    media = sum(pixels) / len(pixels)
    return math.sqrt(sum((p - media) ** 2 for p in pixels) / len(pixels)) < soglia


def avvisi_velocita(tratti) -> list[str]:
    out = []
    for i, (c0, c1, v) in enumerate(tratti, 1):
        if v in (timeline.VEL_MIN, timeline.VEL_MAX):
            troppo = "corto" if v == timeline.VEL_MIN else "lungo"
            out.append(f"ATTENZIONE tratto {i}: velocita' {v:g}x al limite, girato troppo {troppo} per la sua frase")
        elif not 0.8 <= v <= 1.4:
            out.append(f"ATTENZIONE tratto {i}: velocita' {v:.2f}x")
    return out


def avvisi(tl: dict, k: dict, inizio: bytes, fine: bytes, dichiarate=()) -> list[str]:
    out = []
    if not tl["eventi_da_video"]:
        out.append("ATTENZIONE marcatore: cambi letti diversi dagli eventi, tempi dall'orologio (tagli meno precisi)")
    if uniforme(inizio):
        out.append("ATTENZIONE inizio: primi fotogrammi uniformi (pagina bianca o in caricamento)")
    if uniforme(fine):
        out.append("ATTENZIONE fine: ultimi fotogrammi uniformi (pagina bianca o in caricamento)")
    out += avvisi_velocita(k["tratti"])
    fermo = k["durata_voce"] + timeline.CODA - timeline.durata_reel(k["tratti"])
    if fermo > 3:
        out.append(f"ATTENZIONE durata: ultimo fotogramma fermo per {fermo:.1f} s prima della fine")
    registrate = {t for _, t in tl["battute"]}
    mancanti = [b for b in dichiarate if b not in registrate]
    if mancanti:
        out.append("ATTENZIONE battute mai eseguite dalla scena: " + " | ".join(mancanti))
    if not out:
        out.append("OK nessun avviso")
    out.append(f"INFO battute {len(tl['battute'])}, tratti {len(k['tratti'])}, "
               f"reel {timeline.durata_reel(k['tratti']):.1f} s, voce {k['durata_voce']:.1f} s")
    return out


def _durata(video: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _fotogramma(video: Path, t: float, orizzontale: bool = False) -> bytes:
    """Finestra del browser nel reel (sotto la barra), 64x64 in grigi."""
    x, y, w, h = FINESTRA_ORIZZONTALE if orizzontale else FINESTRA
    barra = BARRA_ORIZZONTALE if orizzontale else BARRA
    return subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                           "-vf", f"crop={w}:{h - barra}:{x}:{y + barra},scale=64:64,format=gray",
                           "-f", "rawvideo", "-"], capture_output=True, check=True).stdout


def controlla(cartella: Path, tl: dict, k: dict, dichiarate=(), video: str = "out.mp4",
              orizzontale: bool = False) -> list[str]:
    suffisso = "-16x9" if orizzontale else ""
    video = cartella / video
    durata = _durata(video)
    righe_foglio = max(1, math.ceil(durata * 2 / 11))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf",
                    f"fps=2,scale=200:-1,tile=11x{righe_foglio}", "-frames:v", "1", str(cartella / f"foglio{suffisso}.png")],
                   check=True)
    righe = avvisi(tl, k, _fotogramma(video, 0.25, orizzontale), _fotogramma(video, max(0.0, durata - 0.5), orizzontale),
                   dichiarate)
    (cartella / f"controllo{suffisso}.txt").write_text("\n".join(righe) + "\n", encoding="utf-8")
    print("\n".join(righe))
    print(f"Foglio fotogrammi: {cartella / f'foglio{suffisso}.png'}")
    return righe
