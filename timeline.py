"""Timeline del reel: il progetto di montaggio salvato in work/<slug>/timeline.json e la matematica
dei tempi. Tre orologi:
- girato (s): tempo di rec.webm, quello letto dal marcatore di sincronia;
- pulito (c): girato senza i tagli;
- reel (r): video finito, agganciato alla voce con tratti a velocita' propria."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from montaggio import unisci_tagli
import palette as palette_mod
import voce

VEL_MIN, VEL_MAX = 0.6, 2.5   # oltre si vede che e' accelerato/rallentato: il tratto si satura
CODA = 1.5                    # secondi di video dopo la fine della voce


def pulito(s: float, tagli) -> float:
    """Girato -> girato senza tagli; un istante dentro un taglio finisce all'inizio del taglio."""
    c = s
    for a, b in unisci_tagli(list(tagli)):
        if s >= b:
            c -= b - a
        elif s > a:
            c -= s - a
    return round(c, 3)


def sorgente(c: float, tagli) -> float:
    """Inverso di pulito: istante del girato (il primo dopo eventuali tagli)."""
    s = c
    for a, b in unisci_tagli(list(tagli)):
        if s >= a:
            s += b - a
    return round(s, 3)


def _spezza(tr, t):
    out = []
    for c0, c1, v in tr:
        out += [(c0, t, v), (t, c1, v)] if c0 < t < c1 else [(c0, c1, v)]
    return out


def tratti(durata_pulita: float, durata_voce: float, ancore, forzature=()) -> list[tuple[float, float, float]]:
    """Tratti (c0, c1, velocita) che coprono [0, durata_pulita]. `ancore` = [(c, v)]: la battuta al
    tempo pulito c deve cadere al secondo v della voce. Senza ancore: accelerazione uniforme come
    prima (mai rallentare). `forzature` = [(c0, c1, x)] vincono sulle ancore."""
    fine = durata_voce + CODA
    if not ancore:
        base = [(0.0, durata_pulita, max(1.0, round(durata_pulita / fine, 4)) if durata_pulita else 1.0)]
    else:
        punti = [(0.0, 0.0)] + sorted(ancore, key=lambda p: p[0]) + [(durata_pulita, fine)]
        if any(b[1] <= a[1] for a, b in zip(punti, punti[1:]) if b[0] > a[0]) or \
                [p[1] for p in punti] != sorted(p[1] for p in punti):
            raise ValueError("battute fuori ordine: nel girato e nella voce devono andare avanti insieme")
        base = []
        for (c0, v0), (c1, v1) in zip(punti, punti[1:]):
            if c1 <= c0:
                continue
            base.append((c0, c1, min(max(round((c1 - c0) / (v1 - v0), 4), VEL_MIN), VEL_MAX)))
    for a, b, x in forzature:
        base = _spezza(_spezza(base, a), b)
        base = [(c0, c1, x if a <= c0 and c1 <= b else v) for c0, c1, v in base]
    return base


def mappa(c: float, tr) -> float:
    r = 0.0
    for c0, c1, v in tr:
        if c <= c1:
            return round(r + (c - c0) / v, 3)
        r += (c1 - c0) / v
    c0, c1, v = tr[-1]
    return round(r + (c - c1) / v, 3)


def inversa(r: float, tr) -> float:
    acc = 0.0
    for c0, c1, v in tr:
        d = (c1 - c0) / v
        if r <= acc + d:
            return round(c0 + (r - acc) * v, 3)
        acc += d
    c0, c1, v = tr[-1]
    return round(c1 + (r - acc) * v, 3)


def durata_reel(tr) -> float:
    return round(sum((c1 - c0) / v for c0, c1, v in tr), 3)


def espressione_tempo(tr) -> str:
    """Espressione ffmpeg lineare a tratti: T (tempo pulito, s) -> tempo reel (s)."""
    inizi, r = [], 0.0
    for c0, c1, v in tr:
        inizi.append(r)
        r += (c1 - c0) / v
    c0, _, v = tr[-1]
    espr = f"{inizi[-1]:.4f}+(T-{c0:g})/{v:g}"
    for (c0, c1, v), r0 in reversed(list(zip(tr[:-1], inizi[:-1]))):
        espr = f"if(lt(T,{c1:g}),{r0:.4f}+(T-{c0:g})/{v:g},{espr})"
    return espr


def filtro_tempo(tagli, tr) -> str:
    """Primo pezzo del filtro video: timeline a 30 fps, tagli via, poi tratti a velocita' propria."""
    vf = "fps=30,"
    tagli = unisci_tagli(list(tagli))
    if tagli:
        cond = "+".join(f"between(t,{a:g},{b:g})" for a, b in tagli)
        vf += f"select='not({cond})',"
    return vf + f"setpts=N/30/TB,setpts='({espressione_tempo(tr)})/TB',"


VERSIONE = 1


def da_eventi(eventi, tempi, durata_girato: float | None = None):
    """Eventi del kit (tipo, t_orologio, dati) + tempi veri (dal marcatore, o l'orologio se il
    marcatore non torna) -> tagli, fuochi, battute in tempi del girato. Prima di 'inizio' e' la home:
    tagliata sempre; da 'fine' (pulizia di reel.dopo) alla fine del girato: tagliato anche quello."""
    tagli, fuochi, battute, aperti = [], [], [], []
    for (tipo, _, dati), t in zip(eventi, tempi):
        if tipo == "inizio":
            tagli.append([0.0, t])
        elif tipo == "fine" and durata_girato and t < durata_girato:
            tagli.append([t, durata_girato])
        elif tipo == "fuoco":
            fuochi.append([t, *dati])   # x, y e l'eventuale durata del pan lento
        elif tipo == "battuta":
            battute.append([t, dati])
        elif tipo == "taglio_da":
            aperti.append(t)
        elif tipo == "taglio_a":
            tagli.append([aperti.pop(), t])
    return tagli, fuochi, battute


def nuova(slug, durata_girato, eventi_da_video, tagli, fuochi, battute, testo, hook, zoom, musica,
          palette: str = "verde-smeraldo") -> dict:
    return {"versione": VERSIONE, "slug": slug, "durata_girato": durata_girato,
            "eventi_da_video": eventi_da_video, "tagli": [list(t) for t in tagli],
            "fuochi": sorted([list(f) for f in fuochi], key=lambda f: f[0]), "battute": [list(b) for b in battute],
            "forzature": [], "testo": testo, "hook": hook, "zoom": zoom, "musica": musica,
            "palette": palette}


def carica(cartella: Path) -> dict:
    f = cartella / "timeline.json"
    if not f.exists():
        raise FileNotFoundError(f"Manca {f}: lancia prima 'python capture.py registra {cartella.name}'")
    return json.loads(f.read_text(encoding="utf-8"))


def _storico(cartella: Path) -> list[Path]:
    return sorted(cartella.glob("timeline.*.json"), key=lambda p: int(p.stem.split(".")[1]))


def salva(cartella: Path, tl: dict) -> None:
    """Scrive la timeline; la precedente va nello storico (timeline.N.json), per 'annulla'."""
    f = cartella / "timeline.json"
    if f.exists():
        n = int(_storico(cartella)[-1].stem.split(".")[1]) + 1 if _storico(cartella) else 1
        f.replace(cartella / f"timeline.{n}.json")
    f.write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")


def annulla(cartella: Path) -> dict:
    storico = _storico(cartella)
    if not storico:
        raise ValueError("Niente da annullare: nessuna timeline precedente")
    storico[-1].replace(cartella / "timeline.json")
    return carica(cartella)


def calcola(tl: dict, durata_voce: float, pezzi) -> dict:
    """Dalla timeline (tempi del girato) a cio' che serve al render e al mini editor (tempi reel)."""
    tagli = unisci_tagli([tuple(t) for t in tl["tagli"]])
    ancore, testi = [], []
    for s, testo in tl["battute"]:
        ancore.append((pulito(s, tagli), voce.trova_battuta(testo, pezzi)))
        testi.append(testo)
    forz = [(pulito(a, tagli), pulito(b, tagli), x) for a, b, x in tl["forzature"]]
    tr = tratti(pulito(tl["durata_girato"], tagli), durata_voce, ancore, forz)
    return {"tagli": tagli, "tratti": tr, "durata_voce": durata_voce,
            "fuochi": [(mappa(pulito(s, tagli), tr), *resto) for s, *resto in tl["fuochi"]],
            "battute": [(mappa(c, tr), t) for (c, _), t in zip(ancore, testi)]}


def _girato(tl: dict, k: dict, r: float) -> float:
    if not 0 <= r <= durata_reel(k["tratti"]):
        raise ValueError(f"{r:g} s e' fuori dal reel (0-{durata_reel(k['tratti']):.1f} s)")
    return sorgente(inversa(r, k["tratti"]), k["tagli"])


def _indice(lista: list, n: int, cosa: str) -> int:
    if not 1 <= n <= len(lista):
        raise ValueError(f"{cosa} {n} non esiste (ce ne sono {len(lista)})")
    return n - 1


def op_taglia(tl, k, ra, rb) -> None:
    if rb <= ra:
        raise ValueError("il taglio deve finire dopo l'inizio")
    nuovi = [list(t) for t in k["tagli"]] + [[_girato(tl, k, ra), _girato(tl, k, rb)]]
    tl["tagli"] = [list(t) for t in unisci_tagli([tuple(t) for t in nuovi])]


def op_ripristina(tl, n) -> None:
    tagli = [list(t) for t in unisci_tagli([tuple(t) for t in tl["tagli"]])]
    del tagli[_indice(tagli, n, "Taglio")]
    tl["tagli"] = tagli


def op_velocita(tl, k, ra, rb, x) -> None:
    if rb <= ra or not 0.25 <= x <= 4:
        raise ValueError("intervallo vuoto o velocita' fuori da 0,25-4")
    tl["forzature"].append([_girato(tl, k, ra), _girato(tl, k, rb), x])


def op_fuoco(tl, k, r, x, y) -> None:
    tl["fuochi"] = sorted(tl["fuochi"] + [[_girato(tl, k, r), x, y]], key=lambda f: f[0])


def op_sposta_fuoco(tl, n, dx, dy) -> None:
    f = tl["fuochi"][_indice(tl["fuochi"], n, "Fuoco")]
    f[1], f[2] = f[1] + dx, f[2] + dy


def op_togli_fuoco(tl, n) -> None:
    del tl["fuochi"][_indice(tl["fuochi"], n, "Fuoco")]


def op_zoom(tl, z) -> None:
    if not 1.0 <= z <= 3.0:
        raise ValueError("zoom fuori da 1-3")
    tl["zoom"] = z


def op_hook(tl, testo) -> None:
    righe = [r for r in testo.splitlines() if r.strip()]
    if not righe or len(righe) > 3:
        raise ValueError("l'hook deve avere 1-3 righe")
    tl["hook"] = "\n".join(righe)


PALETTE_DEFAULT = "verde-smeraldo"


def nome_palette(tl: dict) -> str:
    """Timeline scritte prima delle palette: verde-smeraldo, la palette di default."""
    return tl.get("palette", PALETTE_DEFAULT)


def op_palette(tl, nome) -> None:
    palette_mod.per_nome(nome)          # ValueError con l'elenco se non esiste
    tl["palette"] = nome
