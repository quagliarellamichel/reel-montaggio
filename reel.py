"""Mini editor dei reel, a comandi (niente GUI: pensato anche per un agente AI):

    python reel.py <slug> mostra | anteprima T [T...] | taglia A B | ripristina N | velocita A B X
                          fuoco T X Y | sposta-fuoco N DX DY | togli-fuoco N | zoom Z | hook "TESTO"
                          palette NOME | render [--formato orizzontale] | annulla

I tempi sono tempi del REEL (quelli del foglio fotogrammi e delle anteprime); la timeline li salva in
tempi del girato. Ogni modifica lascia la versione precedente in timeline.N.json ('annulla')."""
from __future__ import annotations

import argparse
import copy
import subprocess
import sys
from pathlib import Path

import kit
import montaggio
import render
import timeline
import voce

BASE = Path(__file__).resolve().parent

AVVISO_CARD = ("Attenzione: la card finale e' disegnata nel girato e resta col colore vecchio; "
               "per cambiarla va rigirato (python capture.py registra <slug>).")


def mostra(tl: dict, k: dict) -> str:
    tr = k["tratti"]
    r = [f"reel {timeline.durata_reel(tr):.1f} s · voce {k['durata_voce']:.1f} s · zoom {tl['zoom']:g}"
         f" · palette {timeline.nome_palette(tl)} · hook {tl['hook']!r}"]
    r.append("tagli (girato):")
    r += [f"  {i}. {a:.2f}-{b:.2f}" for i, (a, b) in enumerate(k["tagli"], 1)]
    r.append("tratti (reel):")
    r += [f"  {i}. {timeline.mappa(c0, tr):.2f}-{timeline.mappa(c1, tr):.2f}  velocita' {v:.2f}x"
          for i, (c0, c1, v) in enumerate(tr, 1)]
    r.append("fuochi (reel):")
    for i, f in enumerate(k["fuochi"], 1):
        t, x, y, lento, zoom = montaggio.normalizza_fuoco(f)
        r.append(f"  {i}. {t:.2f}  x={x:.0f} y={y:.0f}" + (f"  lento {lento:g} s" if lento else "")
                 + (f"  zoom {zoom:g}" if zoom else ""))
    r.append("battute (reel):")
    r += [f"  {t:.2f}  {testo}" for t, testo in k["battute"]]
    return "\n".join(r)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reel.py")
    p.add_argument("slug")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mostra")
    sub.add_parser("render").add_argument("--formato", choices=("verticale", "orizzontale"), default="verticale")
    sub.add_parser("annulla")
    sub.add_parser("anteprima").add_argument("t", type=float, nargs="+")
    for nome in ("taglia",):
        s = sub.add_parser(nome)
        s.add_argument("a", type=float)
        s.add_argument("b", type=float)
    sub.add_parser("ripristina").add_argument("n", type=int)
    s = sub.add_parser("velocita")
    for a in ("a", "b", "x"):
        s.add_argument(a, type=float)
    s = sub.add_parser("fuoco")
    for a in ("t", "x", "y"):
        s.add_argument(a, type=float)
    s = sub.add_parser("sposta-fuoco")
    s.add_argument("n", type=int)
    s.add_argument("dx", type=float)
    s.add_argument("dy", type=float)
    sub.add_parser("togli-fuoco").add_argument("n", type=int)
    sub.add_parser("zoom").add_argument("z", type=float)
    sub.add_parser("hook").add_argument("testo")
    sub.add_parser("palette").add_argument("nome")
    return p


def _calcola(work: Path, tl: dict) -> dict:
    pezzi, durata_voce = voce.pezzi_audio(work / "voce.wav", tl["testo"])
    return timeline.calcola(tl, durata_voce, pezzi)


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    work = BASE / "work" / a.slug
    try:
        if not (work / "rec.webm").exists():
            raise FileNotFoundError(f"Manca {work / 'rec.webm'}: lancia prima 'python capture.py registra {a.slug}'")
        if a.cmd == "annulla":
            tl = timeline.annulla(work)
            print(mostra(tl, _calcola(work, tl)))
            return 0
        tl = timeline.carica(work)
        k = _calcola(work, tl)
        if a.cmd == "mostra":
            print(mostra(tl, k))
            return 0
        if a.cmd == "render":
            scenario = BASE / "scenari" / f"{a.slug}.py"
            dichiarate = kit.battute_scenario(scenario) if scenario.exists() else ()
            print(render.produci(a.slug, work, tl, dichiarate, formato=a.formato))
            return 0
        if a.cmd == "anteprima":
            render.render(work, tl, uscita="anteprima.mp4", veloce=True)
            for t in a.t:
                png = work / f"anteprima-{t:g}.png"
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(work / "anteprima.mp4"),
                                "-frames:v", "1", "-vf", "scale=540:-1", str(png)], check=True)
                print(png)
            return 0
        nuova = copy.deepcopy(tl)      # le operazioni lavorano sulla copia: su errore niente cambia
        {"taglia": lambda: timeline.op_taglia(nuova, k, a.a, a.b),
         "ripristina": lambda: timeline.op_ripristina(nuova, a.n),
         "velocita": lambda: timeline.op_velocita(nuova, k, a.a, a.b, a.x),
         "fuoco": lambda: timeline.op_fuoco(nuova, k, a.t, a.x, a.y),
         "sposta-fuoco": lambda: timeline.op_sposta_fuoco(nuova, a.n, a.dx, a.dy),
         "togli-fuoco": lambda: timeline.op_togli_fuoco(nuova, a.n),
         "zoom": lambda: timeline.op_zoom(nuova, a.z),
         "hook": lambda: timeline.op_hook(nuova, a.testo.replace("\\n", "\n")),
         "palette": lambda: timeline.op_palette(nuova, a.nome)}[a.cmd]()
        k = _calcola(work, nuova)      # verifica prima di salvare (battute, tratti)
        timeline.salva(work, nuova)
        print(mostra(nuova, k))
        if a.cmd == "palette":
            print(AVVISO_CARD)
        return 0
    except (ValueError, FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Errore: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
