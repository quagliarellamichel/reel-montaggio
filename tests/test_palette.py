import json

import pytest

import palette

NOMI = ["verde-smeraldo", "blu-mare", "arancio-tramonto", "terracotta", "viola-sera"]


def test_palette_reali_valide_ordinate_e_leggibili():
    ps = palette.tutte()
    assert [p["nome"] for p in ps] == NOMI
    verde = ps[0]
    assert (verde["accento"], verde["contorno_sub"], verde["card_fondo"]) == ("#3ddc84", "#2a3d31", "#2a3331")
    for p in ps:
        assert palette.contrasto(p["testo_chip"], p["accento"]) >= 4.5, p["nome"]
        assert palette.contrasto("#ffffff", p["sfondo"][1]) >= 4.5, p["nome"]
        assert palette.contrasto(p["card_valore"], p["card_fondo"]) >= 4.5, p["nome"]
        assert palette.contrasto(p["card_nota"], p["card_fondo"]) >= 4.5, p["nome"]


def test_valida_campo_mancante_colore_non_valido_sfondo_corto():
    buona = dict(palette.tutte()[0])
    for rotta, msg in ((dict(buona, hook="bianco"), "colore"), ({k: v for k, v in buona.items() if k != "accento"}, "accento"),
                       (dict(buona, sfondo=["#000000"]), "sfondo")):
        with pytest.raises(ValueError, match=msg):
            palette.valida(rotta)


def test_tutte_da_file_rotto(tmp_path):
    f = tmp_path / "p.json"
    f.write_text(json.dumps([{"nome": "x"}]), encoding="utf-8")
    with pytest.raises(ValueError, match="palette x"):
        palette.tutte(f)


def test_prossima_rotazione():
    assert palette.prossima([])["nome"] == "verde-smeraldo"
    assert palette.prossima(["verde-smeraldo"])["nome"] == "blu-mare"
    assert palette.prossima(NOMI)["nome"] == "verde-smeraldo"                     # tutte usate: la piu' vecchia
    assert palette.prossima(NOMI + ["verde-smeraldo"])["nome"] == "blu-mare"
    assert palette.prossima(["rosa-dismessa", "verde-smeraldo"])["nome"] == "blu-mare"  # nome sconosciuto ignorato


def test_prossima_forzata():
    assert palette.prossima(["viola-sera"], forzata="viola-sera")["nome"] == "viola-sera"
    with pytest.raises(ValueError, match="blu-mare"):
        palette.prossima([], forzata="rosa")


def test_usate_sezioni_senza_palette_contano_come_verde():
    testo = ("## A\n- stato: pubblicato\n- video: https://x/a.mp4\n- caption:\n  > a\n\n"
             "## B\n- stato: in-coda\n- video: https://x/b.mp4\n- palette: blu-mare\n- caption:\n  > b\n\n"
             "## C\n- stato: in-coda\n- video: https://x/c.mp4\n- palette: terracotta\n- caption:\n  > c\n")
    assert palette.usate(testo) == ["verde-smeraldo", "blu-mare", "terracotta"]


def test_contrasto_estremi():
    assert palette.contrasto("#000000", "#ffffff") == pytest.approx(21.0)
    assert palette.contrasto("#777777", "#777777") == pytest.approx(1.0)
