import pytest

import timeline as tl
from timeline import CODA, VEL_MAX, VEL_MIN


def _valuta(espr: str, T: float) -> float:
    """Valuta l'espressione ffmpeg di espressione_tempo in Python (if/lt come funzioni)."""
    return eval(espr.replace("if(", "iff("), {"iff": lambda c, a, b: a if c else b,
                                              "lt": lambda a, b: a < b, "T": T})


def test_pulito_e_sorgente_andata_e_ritorno():
    tagli = [(0.0, 1.8), (8.0, 34.0)]
    assert tl.pulito(5.0, tagli) == 3.2
    assert tl.pulito(40.0, tagli) == 12.2
    assert tl.pulito(20.0, tagli) == 6.2          # dentro un taglio: all'inizio del taglio
    for c in (0.0, 3.2, 6.1, 12.2):
        assert tl.pulito(tl.sorgente(c, tagli), tagli) == c


def test_tratti_senza_battute_accelera_in_modo_uniforme_come_oggi():
    assert tl.tratti(32.25, 20.0, []) == [(0.0, 32.25, 1.5)]      # 32,25 / (20 + 1,5)
    assert tl.tratti(10.0, 20.0, []) == [(0.0, 10.0, 1.0)]        # mai rallentare senza battute


def test_tratti_con_battute_velocita_per_tratto():
    tr = tl.tratti(30.0, 18.5, [(10.0, 5.0), (20.0, 15.0)])
    assert tr == [(0.0, 10.0, 2.0), (10.0, 20.0, 1.0), (20.0, 30.0, 2.0)]
    assert tl.durata_reel(tr) == pytest.approx(18.5 + CODA)


def test_tratti_saturano_ai_limiti():
    tr = tl.tratti(30.0, 18.5, [(29.0, 1.0)])
    assert tr[0][2] == VEL_MAX
    tr = tl.tratti(4.0, 18.5, [(2.0, 15.0)])
    assert tr[0][2] == VEL_MIN


def test_tratti_battute_fuori_ordine_errore():
    with pytest.raises(ValueError, match="ordine"):
        tl.tratti(30.0, 18.5, [(20.0, 5.0), (10.0, 15.0)])
    with pytest.raises(ValueError, match="ordine"):
        tl.tratti(30.0, 18.5, [(10.0, 15.0), (20.0, 5.0)])


def test_forzature_spezzano_il_tratto_e_vincono():
    tr = tl.tratti(30.0, 18.5, [], forzature=[(5.0, 10.0, 1.0)])
    assert tr == [(0.0, 5.0, 1.5), (5.0, 10.0, 1.0), (10.0, 30.0, 1.5)]


def test_mappa_e_inversa():
    tr = [(0.0, 10.0, 2.0), (10.0, 20.0, 1.0), (20.0, 30.0, 2.0)]
    assert tl.mappa(10.0, tr) == 5.0
    assert tl.mappa(25.0, tr) == 17.5
    for r in (0.0, 2.5, 5.0, 12.0, 20.0):
        assert tl.mappa(tl.inversa(r, tr), tr) == pytest.approx(r)


def test_espressione_tempo_coincide_con_mappa():
    tr = [(0.0, 10.0, 2.0), (10.0, 20.0, 1.0), (20.0, 30.0, 2.0)]
    espr = tl.espressione_tempo(tr)
    for c in (0.0, 4.0, 10.0, 13.3, 29.0):
        assert _valuta(espr, c) == pytest.approx(tl.mappa(c, tr), abs=1e-3)


def test_filtro_tempo_con_e_senza_tagli():
    tr = [(0.0, 10.0, 1.0)]
    f = tl.filtro_tempo([(8.0, 34.0)], tr)
    assert f.startswith("fps=30,select='not(between(t,8,34))',setpts=N/30/TB,setpts='(")
    assert f.endswith(")/TB',")
    assert "select" not in tl.filtro_tempo([], tr)


import json


def _tl(**k):
    base = tl.nuova(slug="prova", durata_girato=40.0, eventi_da_video=True, tagli=[[0.0, 2.0]],
                    fuochi=[[3.0, 100, 200], [20.0, 300, 400]], battute=[], testo="Ciao. Link in bio.",
                    hook="Riga uno\nRiga due", zoom=1.25, musica="m.mp3")
    base.update(k)
    return base


PEZZI = [(0.0, 2.0, "Hai presente il contratto"), (7.0, 9.0, "Su Acme lo generi"),
         (15.0, 17.0, "Trenta giorni di prova,")]


def test_da_eventi_converte_tagli_fuochi_battute():
    eventi = [("inizio", 1.8, None), ("fuoco", 3.0, (10, 20)), ("taglio_da", 5.0, None),
              ("battuta", 6.0, "Su Acme"), ("taglio_a", 9.0, None)]
    tagli, fuochi, battute = tl.da_eventi(eventi, [1.7, 2.9, 4.9, 5.9, 8.9])
    assert tagli == [[0.0, 1.7], [4.9, 8.9]]
    assert fuochi == [[2.9, 10, 20]]
    assert battute == [[5.9, "Su Acme"]]


def test_salva_crea_storico_e_annulla(tmp_path):
    a = _tl()
    tl.salva(tmp_path, a)
    assert not list(tmp_path.glob("timeline.*.json"))
    b = _tl(zoom=1.5)
    tl.salva(tmp_path, b)
    assert tl.carica(tmp_path)["zoom"] == 1.5
    assert (tmp_path / "timeline.1.json").exists()
    assert tl.annulla(tmp_path)["zoom"] == 1.25
    assert tl.carica(tmp_path)["zoom"] == 1.25
    assert not (tmp_path / "timeline.1.json").exists()


def test_carica_senza_timeline_errore_chiaro(tmp_path):
    with pytest.raises(FileNotFoundError, match="registra"):
        tl.carica(tmp_path)


def test_calcola_senza_battute_e_con_battute():
    k = tl.calcola(_tl(), 18.5, PEZZI)                      # 38 s puliti su 20 s di reel
    assert k["tratti"] == [(0.0, 38.0, 1.9)]
    assert k["fuochi"][0][0] == pytest.approx(1.0 / 1.9, abs=1e-3)
    k = tl.calcola(_tl(battute=[[12.0, "Su Acme lo generi"]]), 18.5, PEZZI)
    assert k["battute"] == [(7.0, "Su Acme lo generi")]


def test_calcola_battuta_non_nel_testo_errore():
    with pytest.raises(ValueError, match="Battuta non trovata"):
        tl.calcola(_tl(battute=[[12.0, "frase sparita"]]), 18.5, PEZZI)


def test_op_taglia_in_tempi_reel_diventa_girato():
    t = _tl()
    k = tl.calcola(t, 18.5, PEZZI)                          # velocita' 1,9
    tl.op_taglia(t, k, 1.0, 2.0)
    assert t["tagli"] == [[0.0, 2.0], [3.9, 5.8]]


def test_op_con_tempi_fuori_dal_reel_errore():
    t = _tl()
    k = tl.calcola(t, 18.5, PEZZI)
    for ra, rb in ((-1.0, 2.0), (5.0, 4.0), (1.0, 99.0)):
        with pytest.raises(ValueError):
            tl.op_taglia(t, k, ra, rb)
    with pytest.raises(ValueError):
        tl.op_fuoco(t, k, 99.0, 1, 1)
    for n in (0, 3):
        with pytest.raises(ValueError):
            tl.op_togli_fuoco(t, n)
    with pytest.raises(ValueError):
        tl.op_ripristina(t, 2)


def test_forzatura_resta_sullo_stesso_girato_dopo_un_taglio():
    t = _tl()
    k = tl.calcola(t, 18.5, PEZZI)
    tl.op_velocita(t, k, 10.0, 12.0, 1.0)
    girato = [list(f) for f in t["forzature"]]
    k = tl.calcola(t, 18.5, PEZZI)
    tl.op_taglia(t, k, 1.0, 2.0)
    assert t["forzature"] == girato                       # salvata in tempi del girato


def test_op_fuoco_sposta_togli_zoom_hook():
    t = _tl()
    k = tl.calcola(t, 18.5, PEZZI)
    tl.op_fuoco(t, k, 5.0, 500, 600)
    assert [f[1] for f in t["fuochi"]] == [100, 500, 300]  # ordinati per tempo
    tl.op_sposta_fuoco(t, 2, 10, -20)
    assert t["fuochi"][1][1:] == [510, 580]
    tl.op_togli_fuoco(t, 2)
    assert len(t["fuochi"]) == 2
    tl.op_zoom(t, 1.4)
    tl.op_hook(t, "Una\nDue")
    assert (t["zoom"], t["hook"]) == (1.4, "Una\nDue")
    with pytest.raises(ValueError):
        tl.op_zoom(t, 0.5)
    with pytest.raises(ValueError):
        tl.op_hook(t, "  ")
    with pytest.raises(ValueError):
        tl.op_hook(t, "a\nb\nc\nd")


def test_palette_nella_timeline_default_e_modifica():
    t = _tl()
    assert t["palette"] == "verde-smeraldo" and tl.nome_palette(t) == "verde-smeraldo"
    del t["palette"]                                   # timeline scritte prima delle palette
    assert tl.nome_palette(t) == "verde-smeraldo"
    tl.op_palette(t, "viola-sera")
    assert tl.nome_palette(t) == "viola-sera"
    with pytest.raises(ValueError, match="inesistente"):
        tl.op_palette(t, "rosa")


def test_da_eventi_porta_la_durata_del_fuoco_lento():
    eventi = [("inizio", 0.5, None), ("fuoco", 1.0, (10, 20)), ("fuoco", 2.0, (30, 40, 5, 1.8))]
    _, fuochi, _ = tl.da_eventi(eventi, [0.5, 1.0, 2.0])
    assert fuochi == [[1.0, 10, 20], [2.0, 30, 40, 5, 1.8]]


def test_da_eventi_fine_taglia_la_pulizia_fino_a_fine_girato():
    eventi = [("inizio", 0.5, None), ("fuoco", 1.0, (10, 20)), ("fine", 9.0, None)]
    tagli, _, _ = tl.da_eventi(eventi, [0.5, 1.0, 9.0], durata_girato=14.0)
    assert tagli == [[0.0, 0.5], [9.0, 14.0]]
    tagli, _, _ = tl.da_eventi(eventi, [0.5, 1.0, 9.0])            # senza durata: come prima
    assert tagli == [[0.0, 0.5]]
