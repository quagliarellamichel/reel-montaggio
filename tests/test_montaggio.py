import re

import montaggio
from montaggio import comando, monta


def test_comando_estende_video_e_taglia_su_voce():
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", "hook.txt", "out.mp4", durata_voce=28.4, font="font.ttf")
    s = " ".join(c)
    assert "tpad=stop_mode=clone" in s              # video più corto della voce: congela l'ultimo frame
    assert c[c.index("-t") + 1] == "29.900"         # voce + 1,5 s
    assert "scale=1080:-2" in s and "pad=1080:1920" in s
    assert "subtitles=sub.srt" in s and "textfile=hook.txt" in s
    assert "expansion=none" in s  # '%' nell'hook (es. "Il 30% in meno") non deve rompere ffmpeg
    for a in ("libx264", "yuv420p", "aac", "48000", "+faststart"):
        assert a in c
    assert c[-1] == "out.mp4"


def test_comando_hook_multiriga_una_drawtext_per_riga():
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt",
                hook=["_hook_riga0.txt", "_hook_riga1.txt"],
                uscita="out.mp4", durata_voce=28.4, font="font.ttf")
    s = " ".join(c)
    assert "textfile=_hook_riga0.txt" in s
    assert "textfile=_hook_riga1.txt" in s
    assert s.count("drawtext=") == 2
    assert s.count("expansion=none") == 2
    ys = re.findall(r"drawtext=[^,]*?:y=(\d+):", s)
    assert len(ys) == 2
    assert ys[0] != ys[1]


def test_monta_divide_hook_multiriga_e_pulisce_stale(tmp_path, monkeypatch):
    (tmp_path / "hook.txt").write_text("Prima riga\nSeconda riga", encoding="utf-8")
    (tmp_path / "_hook_riga5.txt").write_text("stale", encoding="utf-8")

    catturato = {}

    def fake_run(args, cwd, check):
        catturato["args"] = args
        catturato["cwd"] = cwd
        catturato["check"] = check

    monkeypatch.setattr(montaggio.subprocess, "run", fake_run)

    monta(tmp_path, video="rec.webm", voce="voce.wav", musica="m.mp3",
          sottotitoli="sub.srt", hook="hook.txt", uscita="out.mp4",
          durata_voce=28.4, font="font.ttf")

    assert not (tmp_path / "_hook_riga5.txt").exists()
    assert (tmp_path / "_hook_riga0.txt").read_text(encoding="utf-8") == "Prima riga"
    assert (tmp_path / "_hook_riga1.txt").read_text(encoding="utf-8") == "Seconda riga"

    atteso = comando(video="rec.webm", voce="voce.wav", musica="m.mp3", sottotitoli="sub.srt",
                      hook=["_hook_riga0.txt", "_hook_riga1.txt"], uscita="out.mp4",
                      durata_voce=28.4, font="font.ttf")
    assert catturato["args"] == atteso
    assert catturato["cwd"] == tmp_path


def test_hook_ha_box_leggibile_sopra_il_video():
    from montaggio import comando
    s = " ".join(comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", ["_hook_riga0.txt", "_hook_riga1.txt"],
                         "out.mp4", durata_voce=20.0, font="font.ttf"))
    assert s.count("box=1") == 2 and "boxcolor=0x2a3331@0.88" in s


def _valuta(espr: str, t: float) -> float:
    # interprete minimo delle funzioni ffmpeg usate (if, lt) per verificare l'espressione generata
    import re
    py = espr.replace("if(", "_if(").replace("lt(", "_lt(")
    py = re.sub(r"\bt\b", repr(t), py)
    return eval(py, {"_if": lambda c, a, b: a if c else b, "_lt": lambda a, b: a < b})


def test_inquadratura_clamp_e_centro():
    from montaggio import inquadratura
    w, h, pos = inquadratura([(0.0, 960, 540), (5.0, 100, 1070)], zoom=1.25)
    assert (w, h) == (486, 864)
    assert pos[0] == (0.0, 960 - 243, 540 - 432)          # centrato
    assert pos[1] == (5.0, 0, 1080 - 864)                  # clampato ai bordi


def test_espressione_telecamera_fermo_transizione_arrivo():
    from montaggio import espressione
    e = espressione([(0.0, 100), (5.0, 700)], durata=0.7)
    assert _valuta(e, 1.0) == 100                          # fermo sul primo fuoco
    assert _valuta(e, 5.0) == 100                          # parte al momento del fuoco
    assert 100 < _valuta(e, 5.35) < 700                    # a meta' strada
    assert _valuta(e, 6.0) == 700                          # arrivato
    assert "," in e and "\n" not in e


def test_comando_con_fuochi_usa_crop_a_tutto_schermo():
    from montaggio import comando
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540), (4.0, 400, 300)], zoom=1.25)
    s = " ".join(c)
    assert "crop=w=486:h=864:x='" in s and "scale=1080:1920" in s
    assert "pad=1080" not in s


def test_registrazione_piu_lunga_della_voce_viene_accelerata_e_fuochi_riscalati():
    from montaggio import comando
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540), (21.0, 400, 300)], zoom=1.25, durata_video=32.25)
    s = " ".join(c)
    assert "setpts=PTS/1.5" in s             # 32,25 s -> 21,5 s (voce + 1,5)
    assert "lt(t,14)" in s                   # fuoco a 21 s nel girato = 14 s nel reel


def test_comando_con_cornice_video_nella_finestra_senza_drawtext():
    from montaggio import comando, FINESTRA, BARRA
    x, y, w, h = FINESTRA
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540)], zoom=1.25, cornice="cornice.png")
    s = " ".join(c)
    assert f"scale={w}:{h - BARRA}" in s and f"overlay={x}:{y + BARRA}" in s
    assert "drawtext" not in s                       # l'hook sta nella cornice
    assert c[c.index("cornice.png") - 2:c.index("cornice.png")] == ["-loop", "1"] or "-loop" in c


def test_inquadratura_rispetta_proporzioni_della_finestra():
    from montaggio import inquadratura
    w, h, _ = inquadratura([(0.0, 960, 540)], zoom=1.25, aspetto=984 / 1176)
    assert h == 864 and abs(w / h - 984 / 1176) < 0.01


def test_togli_tagli_sposta_i_fuochi_dopo_il_taglio():
    from montaggio import togli_tagli
    fuochi = [(1.0, 10, 10), (5.0, 20, 20), (40.0, 30, 30)]
    assert togli_tagli(fuochi, [(8.0, 34.0)]) == [(1.0, 10, 10), (5.0, 20, 20), (14.0, 30, 30)]
    assert togli_tagli([(20.0, 1, 1)], [(8.0, 34.0)]) == [(8.0, 1, 1)]   # dentro il taglio: all'inizio


def test_comando_con_tagli_rimuove_il_segmento_e_accorcia_la_durata():
    from montaggio import comando
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.srt", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540)], zoom=1.25, durata_video=47.5,
                cornice="cornice.png", tagli=[(8.0, 34.0)])
    s = " ".join(c)
    assert "select='not(between(t,8,34))'" in s and "setpts=N/30/TB" in s
    assert "setpts=PTS/" not in s            # 47,5 - 26 = 21,5 = voce + 1,5: nessuna accelerazione


def test_sottotitoli_ass_senza_force_style():
    from montaggio import comando
    s = " ".join(comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                         font="font.ttf", fuochi=[(0.0, 960, 540)], cornice="cornice.png"))
    assert "subtitles=sub.ass:fontsdir=." in s and "force_style" not in s


def test_classe_pixel_riconosce_solo_rosso_e_blu():
    assert montaggio.classe_pixel(250, 10, 5) == 0
    assert montaggio.classe_pixel(3, 20, 240) == 1
    assert montaggio.classe_pixel(255, 255, 255) is None
    assert montaggio.classe_pixel(42, 51, 49) is None


def test_cambi_marcatore_ignora_frame_senza_marcatore():
    # rosso, pagina in caricamento (None), rosso, blu, None, rosso
    classi = [0, 0, None, None, 0, 1, 1, None, 0]
    assert montaggio.cambi_marcatore(classi, fps=10) == [0.5, 0.8]


def test_unisci_tagli_fonde_le_sovrapposizioni():
    assert montaggio.unisci_tagli([(1.8, 4.7), (0.0, 1.9), (8, 9)]) == [(0.0, 4.7), (8, 9)]


def test_comando_con_tempo_vf_non_riscala_e_usa_preset():
    from montaggio import comando
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540), (14.0, 400, 300)], zoom=1.25, cornice="cornice.png",
                durata_video=90.0, tempo_vf="fps=30,setpts=N/30/TB,setpts='(T)/TB',",
                preset="ultrafast", crf=30)
    s = " ".join(c)
    assert "[0:v]fps=30,setpts=N/30/TB,setpts='(T)/TB',crop=" in s
    assert "setpts=PTS/" not in s and "lt(t,14)" in s       # fuochi gia' in tempi reel
    assert c[c.index("-preset") + 1] == "ultrafast" and c[c.index("-crf") + 1] == "30"


def test_comando_orizzontale_video_nella_finestra_della_cornice_desktop():
    x, y, w, h = montaggio.FINESTRA_ORIZZONTALE
    b = montaggio.BARRA_ORIZZONTALE
    c = comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540), (4.0, 400, 300)], zoom=1.5,
                cornice="cornice-16x9.png", formato="orizzontale")
    s = " ".join(c)
    m = montaggio.MARCATORE_PX
    assert f"crop=1920-{m}:1080-{m}:{m}:{m}," in s               # via il marcatore di sincronia
    assert f"scale={w}:{h - b}" in s and f"overlay={x}:{y + b}" in s
    assert "s=1920x1080" in s and "1080x1920" not in s
    assert "drawtext" not in s                                    # l'hook sta nella cornice
    assert "cornice-16x9.png" in c


def test_espressione_durata_per_punto_pan_lento():
    from montaggio import espressione
    e = espressione([(0.0, 100), (2.0, 700, 5.0)])
    assert 100 < _valuta(e, 4.0) < 700                     # a 2 s dall'inizio del pan lento: ancora in viaggio
    assert _valuta(e, 7.5) == 700


def test_comando_fuoco_lento_nel_filtro():
    s = " ".join(comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                         font="font.ttf", fuochi=[(0.0, 960, 540), (2.0, 400, 300, 5.0)], zoom=1.5,
                         cornice="cornice-16x9.png", formato="orizzontale", tempo_vf=""))
    assert "lt(t,7)" in s                                   # pan dal secondo 2 al 7


def test_espressione_quintica_parte_e_arriva_senza_strappi():
    from montaggio import espressione
    e = espressione([(0.0, 100), (5.0, 700)], durata=1.0)
    assert _valuta(e, 5.5) == 400                          # meta' strada a meta' tempo
    assert _valuta(e, 5.1) < 100 + 600 * 0.02              # parte piano (accelerazione nulla)
    assert _valuta(e, 5.9) > 700 - 600 * 0.02              # si posa piano
    assert _valuta(e, 6.0) == 700


def test_normalizza_fuoco_accetta_le_forme_vecchie():
    from montaggio import normalizza_fuoco
    assert normalizza_fuoco([1.0, 10, 20]) == (1.0, 10, 20, 0, None)
    assert normalizza_fuoco([1.0, 10, 20, 5]) == (1.0, 10, 20, 5, None)
    assert normalizza_fuoco([1.0, 10, 20, 0, 1.8]) == (1.0, 10, 20, 0, 1.8)


def test_telecamera_zona_morta_e_zoom_unico():
    from montaggio import telecamera
    w, h, ex, ey, es = telecamera([(0.0, 960, 540), (3.0, 970, 548)], 1.25)
    assert (w, h) == (486, 864) and es is None
    assert _valuta(ex, 4.0) == _valuta(ex, 0.0) and _valuta(ey, 4.0) == _valuta(ey, 0.0)   # 10 px: non si muove


def test_telecamera_zoom_per_fuoco_scala_il_fotogramma():
    from montaggio import telecamera
    w, h, ex, ey, es = telecamera([(0.0, 960, 540, 0, 1.5), (4.0, 400, 300, 0, 2.0)], 1.5, aspetto=16 / 9)
    assert (w, h) == (1280, 720)                          # ritaglio allo zoom minimo, non cambia mai
    assert _valuta(es, 0.0) == 1 and abs(_valuta(es, 6.0) - 4 / 3) < 1e-4
    assert _valuta(ex, 0.0) == 320                          # zoom 1,5 al centro: x = 960 - 1280/2
    assert _valuta(ex, 6.0) == 0                            # 400 - 960/2 < 0: clamp a 0, poi scalato


def test_comando_con_zoom_per_fuoco_inserisce_la_scala_per_fotogramma():
    s = " ".join(comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                         font="font.ttf", fuochi=[(0.0, 960, 540, 0, 1.5), (4.0, 400, 300, 0, 2.0)], zoom=1.5,
                         cornice="cornice.png", tempo_vf=""))
    assert "scale=w='trunc(iw*(" in s and ":eval=frame,crop=w=" in s


def test_espressione_pan_interrotto_riparte_da_dove_sta_la_camera():
    from montaggio import espressione
    e = espressione([(0.0, 100), (10.0, 700), (10.5, 100)], durata=1.0)
    meta = _valuta(e, 10.5)
    assert 100 < meta < 700                                 # a 10,5 il pan 100->700 e' a meta'
    assert abs(_valuta(e, 10.51) - meta) < 3                # nessun salto: il nuovo pan parte da li'
    assert _valuta(e, 11.5) == 100


def test_togli_tagli_conserva_lento_e_zoom():
    assert montaggio.togli_tagli([(5.0, 10, 20, 1.2, 1.8)], [(1.0, 2.0)]) == [(4.0, 10, 20, 1.2, 1.8)]


def test_orizzontale_senza_cornice_rifiutato():
    import pytest
    with pytest.raises(ValueError):
        comando("rec.webm", "voce.wav", "m.mp3", "sub.ass", "hook.txt", "out.mp4", durata_voce=20.0,
                font="font.ttf", fuochi=[(0.0, 960, 540)], formato="orizzontale")
