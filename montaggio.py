"""Montaggio reel 9:16. Con i fuochi dello scenario: registrazione desktop 1920x1080 ritagliata da una
"telecamera" verticale che segue l'azione (pan morbido tra un fuoco e l'altro) e portata a 1080x1920.
Senza fuochi: registrazione scalata al centro su fondo antracite. Hook in alto, sottotitoli in basso,
voce + musica bassa. Path relativi: su Windows il filtro subtitles non
digerisce 'C:\\' senza escape, quindi ffmpeg gira con cwd nella cartella di lavoro."""
from __future__ import annotations

import subprocess
from pathlib import Path

SFONDO = "0x2a3331"  # antracite del design system
HOOK_Y = 220          # y della prima riga dell'hook
HOOK_RIGA_ALTEZZA = 93  # avanzamento verticale misurato tra due righe a fontsize=64


def _drawtext_hook(font: str, textfile: str, y: int = HOOK_Y) -> str:
    # expansion=none: senza, ffmpeg interpreta '%' dentro il testo come sequenza di espansione
    # drawtext (es. '%{...}'); un hook come "Il 30% in meno" spezza il filtro. Il testo arriva
    # da textfile, mai fidato quanto una costante nel codice.
    return (f"drawtext=fontfile={font}:textfile={textfile}:fontcolor=white:fontsize=64:"
            f"x=(w-text_w)/2:y={y}:line_spacing=12:expansion=none:"
            f"box=1:boxcolor=0x2a3331@0.88:boxborderw=22")


SORGENTE = (1920, 1080)
TRANSIZIONE = 0.9   # secondi di pan tra un fuoco e il successivo (a 0,45 sembrava uno scatto)
ZONA_MORTA = 24     # px: sotto questa distanza la telecamera non si sposta (niente micro-scatti)
FINESTRA = (48, 420, 984, 1240)  # x, y, w, h della finestra browser nella cornice (assets/cornice.html)
BARRA = 64                        # altezza barra del browser: il video sta sotto
RAGGIO = 28
# Spot 16:9 (Google Ads): cornice "desktop" 1920x1080, testo a sinistra e finestra a destra
TELA_ORIZZONTALE = (1920, 1080)
FINESTRA_ORIZZONTALE = (600, 70, 1250, 800)
BARRA_ORIZZONTALE = 56


def inquadratura(fuochi: list[tuple[float, float, float]], zoom: float,
                 sorgente: tuple[int, int] = SORGENTE,
                 aspetto: float = 9 / 16) -> tuple[int, int, list[tuple[float, int, int]]]:
    """Ritaglio alto sorgente/zoom con le proporzioni `aspetto`; per ogni fuoco (t, cx, cy)
    l'angolo in alto a sinistra centrato sul punto e tenuto dentro il fotogramma."""
    sw, sh = sorgente
    h = int(round(sh / zoom)) // 2 * 2
    w = int(round(h * aspetto)) // 2 * 2
    pos = [(t, min(max(int(cx - w / 2), 0), sw - w), min(max(int(cy - h / 2), 0), sh - h))
           for t, cx, cy, *_ in sorted(fuochi)]
    return w, h, pos


# Marcatore di sincronia: 8 px nell'angolo in alto a sinistra del girato, rosso/blu alternati a ogni
# fuoco o taglio. Il video di Playwright resta indietro rispetto all'orologio dello scenario dopo le
# navigazioni pesanti (misurato 2026-09-25: ~1,5 s dopo un solo Ordini/Form), quindi i tempi veri
# degli eventi si leggono dal video e non da time.monotonic().
MARCATORE_PX = 8
MARCATORE_COLORI = ("#ff0000", "#0000ff")


def classe_pixel(r: int, g: int, b: int) -> int | None:
    """0 = rosso, 1 = blu, None = contenuto della pagina (marcatore assente o coperto)."""
    if r > 170 and g < 90 and b < 90:
        return 0
    if b > 170 and r < 90 and g < 90:
        return 1
    return None


def cambi_marcatore(classi: list[int | None], fps: float = 30) -> list[float]:
    """Istanti (s) in cui il marcatore cambia colore: il frame senza marcatore non conta."""
    out, ultimo = [], None
    for n, c in enumerate(classi):
        if c is None:
            continue
        if ultimo is not None and c != ultimo:
            out.append(round(n / fps, 3))
        ultimo = c
    return out


def leggi_marcatore(video: Path, fps: float = 30) -> list[float]:
    """Stessa timeline del montaggio (fps=30 come primo filtro), un pixel al centro del marcatore."""
    # 2x2 e non 1x1: con yuv420 ffmpeg rifiuta i crop di dimensione dispari; conta il primo pixel
    m = MARCATORE_PX // 2 - 1
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"fps={fps:g},crop=2:2:{m}:{m}",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return cambi_marcatore([classe_pixel(*raw[i:i + 3]) for i in range(0, len(raw) - 11, 12)], fps)


def unisci_tagli(tagli: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Tagli sovrapposti fusi in uno: altrimenti durata e fuochi sottrarrebbero due volte."""
    out: list[tuple[float, float]] = []
    for a, b in sorted(tagli):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def togli_tagli(fuochi: list[tuple[float, float, float]],
                tagli: list[tuple[float, float]]) -> list[tuple[float, float, float]]:
    """Riporta i tempi dei fuochi sul girato senza i segmenti tagliati; un fuoco dentro un
    taglio finisce all'istante del taglio."""
    out = []
    for t, *resto in fuochi:
        spostamento = 0.0
        for a, b in sorted(tagli):
            if t >= b:
                spostamento += b - a
            elif t > a:
                spostamento += t - a
        out.append((round(t - spostamento, 3), *resto))
    return out


def normalizza_fuoco(f) -> tuple[float, float, float, float, float | None]:
    """[t, x, y] | [t, x, y, lento] | [t, x, y, lento, zoom] -> (t, x, y, lento, zoom o None).
    Le timeline vecchie hanno 3 valori; `lento` e' la durata del pan di arrivo in secondi DEL REEL
    (non viene scalata dai tratti: la durata di un pan e' una grandezza del video finale), `zoom`
    quello proprio del fuoco (None = zoom della timeline)."""
    t, x, y, *resto = f
    lento = resto[0] if resto and resto[0] else 0
    zoom = resto[1] if len(resto) > 1 and resto[1] else None
    return t, x, y, lento, zoom


def _curva(u: float) -> float:
    return u * u * u * (u * (6 * u - 15) + 10)


def espressione(punti: list[tuple], durata: float = TRANSIZIONE) -> str:
    """Espressione ffmpeg in t: fermo su ogni valore, poi smootherstep (quintica: velocita' E
    accelerazione nulle agli estremi, nessuno strappo) di `durata` secondi verso il successivo a
    partire dal suo istante. Un punto (t, valore, secondi) ha un pan di arrivo tutto suo (fuoco lento).
    Se un punto arriva prima che il pan precedente sia finito, quel pan si interrompe li' e il nuovo
    parte dal valore in cui la camera si trova davvero: niente salto (la velocita' cambia, la
    posizione no)."""
    segmenti, partenza = [], punti[0][1]
    for (t0, a, *_), (t1, b, *propria) in zip(punti, punti[1:]):
        d = propria[0] if propria and propria[0] else durata
        segmenti.append((t1, partenza, b, d))
        partenza = b
    # fine reale di ogni pan e valore in cui viene interrotto dal successivo
    for k in range(len(segmenti) - 1):
        t1, a, b, d = segmenti[k]
        t_succ = segmenti[k + 1][0]
        if t_succ < t1 + d:
            arrivo = a + (b - a) * _curva((t_succ - t1) / d)
            segmenti[k] = (t1, a, arrivo, t_succ - t1)
            segmenti[k + 1] = (t_succ, arrivo, segmenti[k + 1][2], segmenti[k + 1][3])
    espr = f"{segmenti[-1][2] if segmenti else punti[-1][1]:g}"
    for t1, a, b, d in reversed(segmenti):
        u = f"((t-{t1:g})/{d:g})"
        curva = f"{u}*{u}*{u}*({u}*(6*{u}-15)+10)"
        passo = f"{a:g}+({b:g}-{a:g})*{curva}"
        espr = f"if(lt(t,{t1:g}),{a:g},if(lt(t,{t1 + d:g}),{passo},{espr}))"
    return espr


def telecamera(fuochi: list, zoom: float, sorgente: tuple[int, int] = SORGENTE,
               aspetto: float = 9 / 16) -> tuple[int, int, str, str, str | None]:
    """Movimento della telecamera: (w, h, x(t), y(t), s(t)). w x h e' il ritaglio allo zoom minimo
    tra quelli dei fuochi e non cambia mai; un fuoco con zoom maggiore ingrandisce prima il
    fotogramma di s = zoom / zoom_min (scale eval=frame) e ritaglia la stessa w x h. s(t) e' None
    se nessun fuoco ha uno zoom diverso: niente scala intermedia. Fuochi a meno di ZONA_MORTA px
    dal precedente (stesso zoom) restano dove stavano: la camera non trema."""
    fuochi = sorted((normalizza_fuoco(f) for f in fuochi), key=lambda f: f[0])
    zooms = [z or zoom for *_, z in fuochi]
    zb = min(zooms)
    w, h, _ = inquadratura([(0.0, 0, 0)], zb, sorgente, aspetto)
    punti, prec = [], None
    for (t, cx, cy, lento, _), z in zip(fuochi, zooms):
        _, _, [(_, x, y)] = inquadratura([(t, cx, cy)], z, sorgente, aspetto)
        if prec and prec[2] == z and abs(x - prec[0]) < ZONA_MORTA and abs(y - prec[1]) < ZONA_MORTA:
            x, y = prec[0], prec[1]
        prec = (x, y, z)
        s = z / zb
        punti.append((t, round(x * s, 2), round(y * s, 2), round(s, 5), lento))
    ex = espressione([(t, x, l) for t, x, _, _, l in punti])
    ey = espressione([(t, y, l) for t, _, y, _, l in punti])
    es = espressione([(t, s, l) for t, _, _, s, l in punti]) if any(s != 1 for _, _, _, s, _ in punti) else None
    return w, h, ex, ey, es


def _catena_telecamera(fuochi: list, zoom: float, sorgente: tuple[int, int], aspetto: float) -> str:
    """Filtri ffmpeg del ritaglio mobile (con la scala per fotogramma solo se serve)."""
    w, h, ex, ey, es = telecamera(fuochi, zoom, sorgente, aspetto)
    scala = f"scale=w='trunc(iw*({es}))':h='trunc(ih*({es}))':eval=frame," if es else ""
    return f"{scala}crop=w={w}:h={h}:x='{ex}':y='{ey}',"


def comando(video: str, voce: str, musica: str, sottotitoli: str, hook: str | list[str], uscita: str,
            durata_voce: float, font: str, fuochi: list[tuple] | None = None,
            zoom: float = 1.25, durata_video: float | None = None,
            cornice: str | None = None, tagli: list[tuple[float, float]] | None = None,
            tempo_vf: str | None = None, preset: str = "medium", crf: int = 20,
            formato: str = "verticale") -> list[str]:
    # MarginV=33 (non 160): il filtro subtitles, quando l'srt non porta un header ASS con
    # PlayResY, fa scalare a libass i margini come se il video fosse alto 288px (default storico
    # ASS) e poi li riproietta sull'altezza vera — fattore ~6,6x. Con MarginV=160 il sottotitolo
    # finiva quasi a metà schermo invece che in basso; verificato via misura pixel sul frame
    # renderizzato. original_size del filtro subtitles NON compensa questo scaling (verificato
    # non avere alcun effetto misurabile in ffmpeg 8.1), quindi il valore va tarato empiricamente.
    stile = "FontName=Plus Jakarta Sans,FontSize=13,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=33,Alignment=2"
    # .ass porta stile e coordinate reali 1080x1920 (voce.ass); lo stile sopra resta per gli .srt
    filtro_sub = (f"subtitles={sottotitoli}:fontsdir=." if sottotitoli.endswith(".ass")
                  else f"subtitles={sottotitoli}:fontsdir=.:force_style='{stile}'")
    # hook come lista (una riga per file): un drawtext per riga, mai un textfile con newline
    # incorporato — bug noto di ffmpeg (vf_drawtext.c, measure_text(): la lunghezza della
    # sotto-stringa passata a HarfBuzz per ogni riga include il byte di a-capo stesso, quindi
    # HarfBuzz shape-a e disegna un glifo .notdef visibile a fine riga; riproducibile con
    # qualsiasi font, text_shaping=0 non lo evita). Il comando eseguito da monta() è sempre
    # quello che esce da qui: nessuna manipolazione della stringa del filtro dopo comando().
    if isinstance(hook, str):
        hook_dt = _drawtext_hook(font, hook)
    else:
        hook_dt = ",".join(_drawtext_hook(font, f, HOOK_Y + i * HOOK_RIGA_ALTEZZA)
                            for i, f in enumerate(hook))
    if tempo_vf is not None:
        # Timeline (render.py): tagli e tratti a velocita' propria gia' nel filtro, fuochi gia' in
        # tempi del reel
        velocita, fattore = tempo_vf, 1.0
    else:
        # Girato piu' lungo della voce: accelerato in modo uniforme, altrimenti il taglio sulla voce
        # perde il finale (il momento "wow" sta sempre in fondo allo scenario).
        # Tagli (attese lunghe, es. analisi IA): via dal girato prima di tutto il resto
        taglio_vf = ""
        if tagli:
            tagli = unisci_tagli(tagli)
            cond = "+".join(f"between(t,{a:g},{b:g})" for a, b in sorted(tagli))
            taglio_vf = f"fps=30,select='not({cond})',setpts=N/30/TB,"
            if durata_video:
                durata_video -= sum(b - a for a, b in tagli)
            if fuochi:
                fuochi = togli_tagli(fuochi, tagli)
        fattore = max(1.0, (durata_video or 0) / (durata_voce + 1.5))
        velocita = taglio_vf + (f"setpts=PTS/{fattore:g}," if fattore > 1 else "")
    if formato == "orizzontale":
        if not (fuochi and cornice):
            raise ValueError("Il formato orizzontale esiste solo con cornice e almeno un fuoco")
        # Spot 16:9: cornice desktop. Prima via i primi MARCATORE_PX px di bordo, dove sta il
        # marcatore di sincronia rosso/blu (nel 9:16 la telecamera stretta di solito non ci arriva).
        (fx, fy, fw, fh), barra, (tw, th) = FINESTRA_ORIZZONTALE, BARRA_ORIZZONTALE, TELA_ORIZZONTALE
        m = MARCATORE_PX
        sorgente, pre = (SORGENTE[0] - m, SORGENTE[1] - m), f"crop=1920-{m}:1080-{m}:{m}:{m},"
        fuochi = [(t, x - m, y - m, *r) for t, x, y, *r in fuochi or [(0.0, SORGENTE[0] / 2, SORGENTE[1] / 2)]]
    else:
        (fx, fy, fw, fh), barra, (tw, th) = FINESTRA, BARRA, (1080, 1920)
        sorgente, pre = SORGENTE, ""
    if fuochi and cornice:
        # Video dentro la finestra browser della cornice; l'hook e' gia' disegnato nella cornice
        fuochi = [(t / fattore, *r) for t, *r in fuochi]
        vw, vh = fw, fh - barra
        vf = (f"[0:v]{velocita}{pre}{_catena_telecamera(fuochi, zoom, sorgente, vw / vh)}"
              f"scale={vw}:{vh}:flags=lanczos,"
              f"tpad=stop_mode=clone:stop_duration=60,fps=30[vid];"
              f"color=c={SFONDO}:s={tw}x{th}:r=30[bg];[bg][vid]overlay={fx}:{fy + barra}:shortest=1[b1];"
              f"[b1][3:v]overlay=0:0,{filtro_sub}[v];"
              f"[2:a]volume=0.12[m];[1:a][m]amix=inputs=2:duration=first:normalize=0,apad[a]")
        return ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", video, "-i", voce, "-stream_loop", "-1", "-i", musica, "-loop", "1", "-i", cornice,
                "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
                "-t", f"{durata_voce + 1.5:.3f}",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", preset, "-crf", str(crf),
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                "-movflags", "+faststart", uscita]
    elif fuochi:
        fuochi = [(t / fattore, *r) for t, *r in fuochi]
        video_vf = f"[0:v]{velocita}{_catena_telecamera(fuochi, zoom, SORGENTE, 9 / 16)}scale=1080:1920:flags=lanczos,"
    else:
        video_vf = f"[0:v]{velocita}scale=1080:-2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={SFONDO},"
    vf = (f"{video_vf}"
          f"tpad=stop_mode=clone:stop_duration=60,fps=30,"
          f"{hook_dt},"
          f"{filtro_sub}[v];"
          f"[2:a]volume=0.12[m];[1:a][m]amix=inputs=2:duration=first:normalize=0,apad[a]")
    return ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", video, "-i", voce, "-stream_loop", "-1", "-i", musica,
            "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
            "-t", f"{durata_voce + 1.5:.3f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", preset, "-crf", str(crf),
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
            "-movflags", "+faststart", uscita]


def monta(cartella: Path, **kw) -> None:
    for stale in cartella.glob("_hook_riga*.txt"):
        stale.unlink()
    hook_path = cartella / kw["hook"]
    righe = [r for r in hook_path.read_text(encoding="utf-8").splitlines() if r.strip()]
    if len(righe) > 1:
        nomi = []
        for i, riga in enumerate(righe):
            nomefile = f"_hook_riga{i}.txt"
            (cartella / nomefile).write_text(riga, encoding="utf-8")
            nomi.append(nomefile)
        kw = {**kw, "hook": nomi}
    subprocess.run(comando(**kw), cwd=cartella, check=True)
