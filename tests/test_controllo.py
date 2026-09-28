import controllo

VARIO = bytes((i * 37) % 256 for i in range(64 * 64))
BIANCO = bytes([250] * (64 * 64))


def _k(tratti, durata_voce=18.5):
    return {"tratti": tratti, "durata_voce": durata_voce, "tagli": [], "fuochi": [], "battute": []}


def _tl(**x):
    base = {"eventi_da_video": True, "battute": []}
    base.update(x)
    return base


def test_uniforme():
    assert controllo.uniforme(BIANCO)
    assert not controllo.uniforme(VARIO)
    assert not controllo.uniforme(b"")


def test_avvisi_velocita_limiti_e_saturazione():
    righe = controllo.avvisi_velocita([(0, 5, 1.0), (5, 10, 1.7), (10, 20, 2.5), (20, 22, 0.6)])
    assert len(righe) == 3
    assert "1.70" in righe[0]
    assert "limite" in righe[1] and "limite" in righe[2]


def test_avvisi_tutto_ok():
    righe = controllo.avvisi(_tl(), _k([(0.0, 20.0, 1.0)]), VARIO, VARIO)
    assert righe[0].startswith("OK")


def test_avvisi_marcatore_inizio_bianco_video_fermo_battute_mancanti():
    righe = controllo.avvisi(_tl(eventi_da_video=False, battute=[[3.0, "Ecco"]]),
                             _k([(0.0, 10.0, 1.0)]), BIANCO, VARIO, dichiarate=["Ecco", "Link in bio"])
    testo = "\n".join(righe)
    assert "marcatore" in testo
    assert "inizio" in testo
    assert "fermo" in testo                     # 10 s di video su 20 s di voce + coda
    assert "Link in bio" in testo
    assert not any(r.startswith("OK") for r in righe)
