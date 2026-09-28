"""Produzione locale dei reel: login al sito, registrazione dello scenario, voce, montaggio."""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

import kit
import montaggio
import palette
import render
import timeline
import voce

BASE = Path(__file__).resolve().parent
AUTH = BASE / ".auth.json"
# Campi sfocati in ogni girato, oltre ai SENSIBILI dello scenario (la mask Playwright non vale per i video).
SENSIBILI_DEFAULT = ["input[type=email]", "input[type=tel]", ".user-name", ".navbar .dropdown-toggle"]


def css_blur(selettori: list[str]) -> str:
    return ", ".join(SENSIBILI_DEFAULT + list(selettori)) + " { filter: blur(8px) !important; }"


def _base_url() -> str:
    url = os.environ.get("REEL_BASE_URL")
    if not url:
        sys.exit("Manca REEL_BASE_URL in .env (es. https://app.example.com)")
    return url.rstrip("/")


def scegli_palette(sc, forzata: str | None = None) -> dict:
    """Palette di turno (la meno usata di recente in reels.md), oppure quella forzata da riga di
    comando (--palette, vince) o dallo scenario (PALETTE)."""
    reels = BASE / "reels.md"
    testo = reels.read_text(encoding="utf-8") if reels.exists() else ""
    return palette.prossima(palette.usate(testo), forzata or getattr(sc, "PALETTE", None))


def _durata(file: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(file)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def login() -> None:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=False)
        ctx = b.new_context(viewport={"width": 1920, "height": 1080})
        ctx.new_page().goto(_base_url() + os.environ.get("REEL_LOGIN_PATH", "/"))
        input("Accedi nel browser (meglio un account demo), poi premi Invio qui… ")
        ctx.storage_state(path=str(AUTH))
        b.close()
    print(f"Sessione salvata in {AUTH}")


def valida_battute(percorso: Path, testo: str) -> list[str]:
    """Ogni reel.battuta("...") dello scenario deve agganciarsi al TESTO, in ordine di comparsa nella
    voce e mai sul primissimo pezzo di sottotitolo (t=0): controllato prima di aprire il browser,
    cosi' un refuso non costa credito ne' OTP. Stesse due condizioni che timeline.tratti rifiuta
    (battute fuori ordine, ancora a v=0 con c>0), ma qui il fallimento e' prima della registrazione
    invece che dentro render.produci a girato gia' fatto."""
    pezzi = [(0.0, 0.0, p) for p in voce.pezzi_testo(testo)]
    battute = kit.battute_scenario(percorso)
    precedente = -1
    for b in battute:
        i = voce.indice_battuta(b, pezzi)
        if i == 0:
            raise ValueError(f"Battuta sul primo pezzo di sottotitolo (tempo 0 della voce), non puo' "
                             f"fare da ancora: {b!r}")
        if i <= precedente:
            raise ValueError(f"Battute fuori ordine rispetto alla voce: {b!r} deve comparire dopo le "
                             f"battute precedenti dello scenario")
        precedente = i
    return battute


def _prepara_asset(slug: str, work: Path, sc) -> None:
    musiche = sorted((BASE / "music").glob("*.mp3"))
    (work / "m.mp3").write_bytes(musiche[sum(map(ord, slug)) % len(musiche)].read_bytes())  # rotazione deterministica
    (work / "font.ttf").write_bytes((BASE / "assets" / "PlusJakartaSans-Bold.ttf").read_bytes())
    # sottotitoli: istanza statica ExtraBold (libass con il font variabile disegna solo il peso normale)
    (work / "font-sub.ttf").write_bytes((BASE / "assets" / "PlusJakartaSans-ExtraBold.ttf").read_bytes())
    (work / "caption.txt").write_text(sc.CAPTION, encoding="utf-8")


def _voce(work: Path, testo: str, forza: bool) -> None:
    if forza or not voce.voce_attuale(work, testo):
        voce.sintetizza_verificata(testo, os.environ["GEMINI_API_KEY"], work / "voce.wav")
        voce.segna_voce(work, testo)
    else:
        print("Voce riusata: TESTO invariato")


def registra(slug: str, voce_nuova: bool = False, palette_forzata: str | None = None) -> Path:
    from playwright.sync_api import sync_playwright
    if not AUTH.exists():
        sys.exit("Manca .auth.json: lancia prima 'python capture.py login'")
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Manca GEMINI_API_KEY in .env")
    sc = importlib.import_module(f"scenari.{slug}")
    try:
        dichiarate = valida_battute(BASE / "scenari" / f"{slug}.py", sc.TESTO)
    except ValueError as e:
        sys.exit(str(e))
    try:
        pal = scegli_palette(sc, palette_forzata)
    except ValueError as e:
        sys.exit(str(e))
    print(f"Palette: {pal['nome']}")
    work = BASE / "work" / slug
    work.mkdir(parents=True, exist_ok=True)
    for f in work.glob("*.webm"):
        if f.name != "rec.webm":      # il girato buono resta finche' non ce n'e' uno nuovo
            f.unlink()

    style = css_blur(sc.SENSIBILI).replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    errore = None
    with sync_playwright() as p:
        b = p.chromium.launch()
        # Desktop 1920x1080 col layout normale (il gestionale non e' responsive): il verticale lo fa
        # il montaggio, con una telecamera 9:16 che segue i fuochi dichiarati dallo scenario.
        ctx = b.new_context(storage_state=str(AUTH), viewport={"width": 1920, "height": 1080},
                            record_video_dir=str(work), record_video_size={"width": 1920, "height": 1080})
        ctx.add_init_script(f"document.addEventListener('DOMContentLoaded', () => {{"
                            f" const s = document.createElement('style'); s.textContent = `{style}`;"
                            f" document.head.appendChild(s); }});")
        # Marcatore di sincronia (vedi montaggio.MARCATORE_PX): ridisegnato a ogni documento col
        # colore corrente del Reel, cambiato a ogni evento. Script e funzione esposta PRIMA di
        # creare la pagina; la lambda legge `reel` solo quando la pagina la chiama (dopo il goto).
        ctx.expose_function("__reelColore", lambda: reel.colore)
        ctx.add_init_script(
            "(() => { const px = %d; const draw = c => { let d = document.getElementById('__rm');"
            " if (!d) { d = document.createElement('div'); d.id = '__rm'; d.style.cssText ="
            " `position:fixed;left:0;top:0;width:${px}px;height:${px}px;z-index:2147483647;pointer-events:none`;"
            " (document.body || document.documentElement).appendChild(d); } d.style.background = c; };"
            " window.__rmDraw = draw; const go = () => window.__reelColore().then(draw);"
            " if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', go); else go(); })();"
            % montaggio.MARCATORE_PX)
        page = ctx.new_page()
        reel = kit.Reel(page, colori=montaggio.MARCATORE_COLORI, palette=pal)
        page.goto(_base_url() + "/")
        if os.environ.get("REEL_LOGIN_PATH", "/auth/login") in page.url:
            sys.exit("Sessione scaduta: rilancia 'python capture.py login'")
        page.locator("#__rm").wait_for()
        page.wait_for_timeout(500)   # il rosso iniziale deve finire nel video, o il primo cambio non si vede
        reel.inizio()                # la home prima dello scenario non va nel reel
        try:
            kit.esegui_scena(sc, page, reel)
        except BaseException as e:   # anche Ctrl+C: il girato parziale serve a capire dov'e' caduta
            errore = e
        # Playwright registra un video per ogni pagina (anche i popup): serve quello della principale
        principale = Path(page.video.path()) if page.video else None
        ctx.close()
        b.close()
    if errore is not None:
        if principale is not None and principale.exists():
            principale.replace(work / "rec-fallito.webm")
            print(f"Girato parziale: {work / 'rec-fallito.webm'} (timeline precedente invariata)")
        raise errore
    if principale is None or not principale.exists():
        sys.exit(f"Nessun video registrato in {work}")
    principale.replace(work / "rec.webm")
    for altro in work.glob("*.webm"):
        if altro.name != "rec.webm":
            altro.unlink()

    letti = montaggio.leggi_marcatore(work / "rec.webm")
    da_video = len(letti) == len(reel.eventi)
    tempi = letti if da_video else [t for _, t, _ in reel.eventi]
    durata_girato = _durata(work / "rec.webm")
    tagli, fuochi, battute = timeline.da_eventi(reel.eventi, tempi, durata_girato)
    # Timeline salvata SUBITO, prima della voce: dipende solo da TESTO/HOOK/eventi, non dall'audio.
    # Se Gemini fallisce dopo, il girato nuovo resta comunque agganciato alla sua timeline (non a
    # quella di un take precedente) e 'python capture.py voce <slug>' puo' ritentare la sola voce.
    tl = timeline.nuova(slug=slug, durata_girato=durata_girato, eventi_da_video=da_video,
                        tagli=tagli, fuochi=fuochi, battute=battute, testo=sc.TESTO, hook=sc.HOOK,
                        zoom=getattr(sc, "ZOOM_TELECAMERA", 1.25), musica="m.mp3", palette=pal["nome"])
    if getattr(sc, "CHIP", None):   # etichetta della cornice (9:16 e 16:9), default "NOVITÀ"
        tl["chip"] = sc.CHIP
    timeline.salva(work, tl)
    _prepara_asset(slug, work, sc)
    _voce(work, sc.TESTO, voce_nuova)
    return _fine(slug, work, tl, dichiarate, sc)


def rivoce(slug: str) -> Path:
    """Nuovo TESTO sullo stesso girato: rifa' voce e render, le battute devono ancora combaciare."""
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("Manca GEMINI_API_KEY in .env")
    sc = importlib.import_module(f"scenari.{slug}")
    work = BASE / "work" / slug
    tl = timeline.carica(work)
    try:
        dichiarate = valida_battute(BASE / "scenari" / f"{slug}.py", sc.TESTO)
    except ValueError as e:
        sys.exit(str(e))
    tl["testo"] = sc.TESTO
    _voce(work, sc.TESTO, forza=False)
    (work / "caption.txt").write_text(sc.CAPTION, encoding="utf-8")
    timeline.salva(work, tl)
    return _fine(slug, work, tl, dichiarate, sc)


def _fine(slug: str, work: Path, tl: dict, dichiarate, sc) -> Path:
    out = render.produci(slug, work, tl, dichiarate)
    print(f"\nVideo: {out}\n--- caption ---\n{sc.CAPTION}\n\n"
          f"Ritocchi: python reel.py {slug} mostra | taglia | fuoco | velocita | render\n"
          )
    if hasattr(os, "startfile"):
        os.startfile(out)  # Windows: apre il player
    return out


def _opzione(nome: str) -> str | None:
    """Valore di un'opzione '--nome VALORE' dopo lo slug, None se assente."""
    resto = sys.argv[3:]
    return resto[resto.index(nome) + 1] if nome in resto[:-1] else None


def main() -> int:
    load_dotenv(BASE / ".env")
    comandi = ("login", "registra", "voce")
    if len(sys.argv) < 2 or sys.argv[1] not in comandi or (sys.argv[1] != "login" and len(sys.argv) < 3):
        print("uso: python capture.py login | registra <slug> [--voce-nuova] [--palette NOME] | voce <slug>")
        return 2
    if sys.argv[1] != "login":
        slug = sys.argv[2]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            print("slug non valido: solo a-z, 0-9 e '-'")
            return 2
    try:
        {"login": lambda: login(),
         "registra": lambda: registra(sys.argv[2], voce_nuova="--voce-nuova" in sys.argv[3:],
                                      palette_forzata=_opzione("--palette")),
         "voce": lambda: rivoce(sys.argv[2])}[sys.argv[1]]()
    except (RuntimeError, subprocess.CalledProcessError) as e:
        print(f"Errore: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
