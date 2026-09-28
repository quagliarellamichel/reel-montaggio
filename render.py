"""Render di un reel dalla sua timeline (work/<slug>/timeline.json): sottotitoli, cornice, ffmpeg,
controllo. Nessun altro input: tutto cio' che si puo' correggere sta nella timeline."""
from __future__ import annotations

import shutil
from pathlib import Path

import controllo
import montaggio
import palette
import timeline
import voce

BASE = Path(__file__).resolve().parent


def rendi_cornice(hook: str, dest: Path, pal: dict, chip: str | None = None, orizzontale: bool = False) -> None:
    """Cornice del reel (sfondo, chip, hook, finestra browser col buco) come PNG trasparente,
    nei colori della palette; `orizzontale` = cornice desktop 1920x1080 dello spot."""
    from playwright.sync_api import sync_playwright
    x, y, w, h = montaggio.FINESTRA_ORIZZONTALE if orizzontale else montaggio.FINESTRA
    barra = montaggio.BARRA_ORIZZONTALE if orizzontale else montaggio.BARRA
    tw, th = montaggio.TELA_ORIZZONTALE if orizzontale else (1080, 1920)
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": tw, "height": th})
        pg.goto((BASE / "assets" / "cornice.html").as_uri())
        pg.evaluate("g => window.componi(g)", {"hook": hook, "chip": chip, "x": x, "y": y, "w": w, "h": h,
                                               "barra": barra, "raggio": montaggio.RAGGIO,
                                               "palette": pal, "orizzontale": orizzontale})
        pg.screenshot(path=str(dest), omit_background=True)
        b.close()


def _cornice(cartella: Path, hook: str, pal: dict, chip: str | None = None, orizzontale: bool = False) -> str:
    nome = "cornice-16x9" if orizzontale else "cornice"
    segno = cartella / f"{nome}.txt"
    atteso = f"{pal['nome']}\x1f{hook}\x1f{chip or ''}"   # si rifa' se cambia hook, palette o chip
    if (cartella / f"{nome}.png").exists() and segno.exists() and segno.read_text(encoding="utf-8") == atteso:
        return f"{nome}.png"
    rendi_cornice(hook, cartella / f"{nome}.png", pal, chip, orizzontale=orizzontale)
    segno.write_text(atteso, encoding="utf-8")
    return f"{nome}.png"


def _prepara_font(cartella: Path) -> None:
    """I font non stanno nel progetto di lavoro (sono nel repo, vedi capture._prepara_asset): un progetto
    ripristinato con 'recupera' o una cartella nuova senza passare da 'registra' non li hanno ancora.
    Li ricopia da assets/ solo se mancano, senza toccare quelli gia' presenti."""
    for nome, sorgente in (("font.ttf", "PlusJakartaSans-Bold.ttf"),
                           ("font-sub.ttf", "PlusJakartaSans-ExtraBold.ttf")):
        dest = cartella / nome
        if not dest.exists():
            dest.write_bytes((BASE / "assets" / sorgente).read_bytes())


def render(cartella: Path, tl: dict, uscita: str = "out.mp4", veloce: bool = False,
           formato: str = "verticale") -> dict:
    _prepara_font(cartella)
    pal = palette.per_nome(timeline.nome_palette(tl))
    pezzi, durata_voce = voce.pezzi_audio(cartella / "voce.wav", tl["testo"])
    orizzontale = formato == "orizzontale"
    (cartella / "sub.ass").write_text(voce.ass(pezzi, contorno=pal["contorno_sub"], orizzontale=orizzontale),
                                      encoding="utf-8")
    (cartella / "hook.txt").write_text(tl["hook"], encoding="utf-8")
    cornice = _cornice(cartella, tl["hook"], pal, tl.get("chip"), orizzontale)
    k = timeline.calcola(tl, durata_voce, pezzi)
    montaggio.monta(cartella, video="rec.webm", voce="voce.wav", musica=tl["musica"], sottotitoli="sub.ass",
                    hook="hook.txt", uscita=uscita, durata_voce=durata_voce, font="font.ttf",
                    fuochi=k["fuochi"] or None, zoom=tl["zoom"], cornice=cornice,
                    tempo_vf=timeline.filtro_tempo(k["tagli"], k["tratti"]),
                    preset="ultrafast" if veloce else "medium", crf=30 if veloce else 20, formato=formato)
    return k


def produci(slug: str, cartella: Path, tl: dict, dichiarate=(), formato: str = "verticale") -> Path:
    """Render completo + controllo + copia in out/<slug>.mp4 (il file da pubblicare).
    Lo spot 16:9 esce in out/<slug>-16x9.mp4."""
    uscita = "out-16x9.mp4" if formato == "orizzontale" else "out.mp4"
    k = render(cartella, tl, uscita=uscita, formato=formato)
    controllo.controlla(cartella, tl, k, dichiarate, video=uscita, orizzontale=formato == "orizzontale")
    out = BASE / "out" / (f"{slug}-16x9.mp4" if formato == "orizzontale" else f"{slug}.mp4")
    out.parent.mkdir(exist_ok=True)
    shutil.copyfile(cartella / uscita, out)
    return out
