import json
import subprocess

import pytest

import reel
import timeline

PEZZI = [(0.0, 2.0, "Hai presente il contratto"), (7.0, 9.0, "Su Acme lo generi"),
         (15.0, 17.0, "Trenta giorni di prova,")]


@pytest.fixture
def work(tmp_path, monkeypatch):
    w = tmp_path / "work" / "prova"
    w.mkdir(parents=True)
    (w / "rec.webm").write_bytes(b"x")
    (w / "voce.wav").write_bytes(b"x")
    timeline.salva(w, timeline.nuova(slug="prova", durata_girato=40.0, eventi_da_video=True,
                                     tagli=[[0.0, 2.0]], fuochi=[[3.0, 100, 200]], battute=[],
                                     testo="x", hook="Uno", zoom=1.25, musica="m.mp3"))
    monkeypatch.setattr(reel, "BASE", tmp_path)
    monkeypatch.setattr(reel.voce, "pezzi_audio", lambda wav, testo: (PEZZI, 18.5))
    return w


def test_taglia_salva_storico_e_mostra(work, capsys):
    assert reel.main(["prova", "taglia", "1", "2"]) == 0
    assert timeline.carica(work)["tagli"] == [[0.0, 2.0], [3.9, 5.8]]
    assert (work / "timeline.1.json").exists()
    assert "tagli" in capsys.readouterr().out


def test_errore_non_tocca_la_timeline(work, capsys):
    prima = (work / "timeline.json").read_text(encoding="utf-8")
    assert reel.main(["prova", "taglia", "5", "99"]) == 1
    assert reel.main(["prova", "togli-fuoco", "7"]) == 1
    assert (work / "timeline.json").read_text(encoding="utf-8") == prima
    assert not list(work.glob("timeline.*.json"))
    assert "fuori dal reel" in capsys.readouterr().out


def test_annulla(work):
    reel.main(["prova", "zoom", "1.5"])
    assert reel.main(["prova", "annulla"]) == 0
    assert timeline.carica(work)["zoom"] == 1.25


def test_fuoco_sposta_hook(work):
    assert reel.main(["prova", "fuoco", "5", "500", "600"]) == 0
    assert reel.main(["prova", "sposta-fuoco", "2", "10", "-20"]) == 0
    assert reel.main(["prova", "hook", "Riga uno\\nRiga due"]) == 0
    t = timeline.carica(work)
    assert t["fuochi"][1][1:] == [510, 580] and t["hook"] == "Riga uno\nRiga due"


def test_senza_registrazione_errore(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(reel, "BASE", tmp_path)
    assert reel.main(["mai-girato", "mostra"]) == 1
    assert "registra" in capsys.readouterr().out


def test_render_usa_produci(work, monkeypatch):
    fatti = []
    monkeypatch.setattr(reel.render, "produci",
                        lambda slug, cartella, tl, dichiarate=(), formato="verticale": fatti.append((slug, formato)))
    assert reel.main(["prova", "render"]) == 0
    assert reel.main(["prova", "render", "--formato", "orizzontale"]) == 0
    assert fatti == [("prova", "verticale"), ("prova", "orizzontale")]


def test_anteprima_ffmpeg_error(work, monkeypatch, capsys):
    monkeypatch.setattr(reel.render, "render", lambda *args, **kwargs: None)
    monkeypatch.setattr(reel.subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(
        subprocess.CalledProcessError(1, ["ffmpeg"])))
    assert reel.main(["prova", "anteprima", "1"]) == 1
    assert "Errore" in capsys.readouterr().out


def test_comando_palette_salva_e_avvisa_della_card(work, capsys):
    assert reel.main(["prova", "palette", "blu-mare"]) == 0
    assert timeline.carica(work)["palette"] == "blu-mare"
    out = capsys.readouterr().out
    assert "card" in out and "palette blu-mare" in out
    prima = (work / "timeline.json").read_text(encoding="utf-8")
    assert reel.main(["prova", "palette", "rosa"]) == 1
    assert (work / "timeline.json").read_text(encoding="utf-8") == prima
