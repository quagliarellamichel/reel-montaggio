import render
import timeline


def test_render_passa_timeline_e_tempi_reel_a_monta(tmp_path, monkeypatch):
    pezzi = [(0.0, 3.0, "Hai presente"), (5.0, 8.0, "Su Acme lo generi"), (15.0, 18.0, "Link in bio.")]
    monkeypatch.setattr(render.voce, "pezzi_audio", lambda wav, testo: (pezzi, 18.5))
    cornici = []
    monkeypatch.setattr(render, "rendi_cornice",
                        lambda hook, dest, pal, chip=None, orizzontale=False: (cornici.append(hook), dest.write_bytes(b"png")))
    chiamate = {}
    monkeypatch.setattr(render.montaggio, "monta", lambda cartella, **kw: chiamate.update(kw))
    tl = timeline.nuova(slug="p", durata_girato=40.0, eventi_da_video=True, tagli=[[0.0, 2.0]],
                        fuochi=[[3.0, 100, 200]], battute=[[12.0, "Su Acme lo generi"]],
                        testo="x", hook="Uno\nDue", zoom=1.3, musica="m.mp3")
    k = render.render(tmp_path, tl)
    assert chiamate["tempo_vf"] == timeline.filtro_tempo(k["tagli"], k["tratti"])
    assert chiamate["fuochi"] == k["fuochi"] and chiamate["zoom"] == 1.3
    assert (tmp_path / "hook.txt").read_text(encoding="utf-8") == "Uno\nDue"
    assert "Dialogue" in (tmp_path / "sub.ass").read_text(encoding="utf-8")
    render.render(tmp_path, tl)                     # stesso hook: cornice non rifatta
    assert cornici == ["Uno\nDue"]
    tl["hook"] = "Nuovo"
    render.render(tmp_path, tl)
    assert cornici == ["Uno\nDue", "Nuovo"]


def _setup(tmp_path, monkeypatch, cornici):
    pezzi = [(0.0, 3.0, "Hai presente"), (15.0, 18.0, "Link in bio.")]
    monkeypatch.setattr(render.voce, "pezzi_audio", lambda wav, testo: (pezzi, 18.5))
    monkeypatch.setattr(render, "rendi_cornice",
                        lambda hook, dest, pal, chip=None, orizzontale=False: (cornici.append((hook, pal["nome"]) + ((chip,) if chip else ())), dest.write_bytes(b"png")))
    monkeypatch.setattr(render.montaggio, "monta", lambda cartella, **kw: None)
    return timeline.nuova(slug="p", durata_girato=20.0, eventi_da_video=True, tagli=[], fuochi=[[1.0, 100, 200]],
                          battute=[], testo="x", hook="Uno", zoom=1.25, musica="m.mp3")


def test_render_applica_la_palette_a_cornice_e_sottotitoli(tmp_path, monkeypatch):
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    tl["palette"] = "blu-mare"
    render.render(tmp_path, tl)
    assert cornici == [("Uno", "blu-mare")]
    assert ",&H0050351B," in (tmp_path / "sub.ass").read_text(encoding="utf-8")
    render.render(tmp_path, tl)
    assert len(cornici) == 1                              # stessa palette e hook: cache
    tl["palette"] = "viola-sera"
    render.render(tmp_path, tl)
    assert cornici[-1] == ("Uno", "viola-sera")


def test_render_timeline_vecchia_senza_palette_resta_verde(tmp_path, monkeypatch):
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    del tl["palette"]
    render.render(tmp_path, tl)
    assert cornici == [("Uno", "verde-smeraldo")]
    assert ",&H00313D2A," in (tmp_path / "sub.ass").read_text(encoding="utf-8")


def test_render_prepara_i_font_se_mancanti(tmp_path, monkeypatch):
    """Progetto ripristinato (recupera) o nuovo senza font nella cartella: render li ricopia da
    assets/ prima del montaggio, stessi sorgenti di capture._prepara_asset."""
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    render.render(tmp_path, tl)
    assert (tmp_path / "font.ttf").read_bytes() == (render.BASE / "assets" / "PlusJakartaSans-Bold.ttf").read_bytes()
    assert (tmp_path / "font-sub.ttf").read_bytes() == \
        (render.BASE / "assets" / "PlusJakartaSans-ExtraBold.ttf").read_bytes()


def test_render_non_sovrascrive_font_gia_presente(tmp_path, monkeypatch):
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    (tmp_path / "font.ttf").write_bytes(b"gia' presente")
    render.render(tmp_path, tl)
    assert (tmp_path / "font.ttf").read_bytes() == b"gia' presente"


def test_cornice_html_usa_variabili_css():
    from pathlib import Path
    html = (Path(render.BASE) / "assets" / "cornice.html").read_text(encoding="utf-8")
    for var in ("--sfondo1", "--sfondo2", "--sfondo3", "--accento", "--testo-chip", "--hook"):
        assert f"var({var})" in html
    assert "palette" in html                               # componi() riceve la palette


def test_render_orizzontale_cornice_desktop_e_sottotitoli_1920(tmp_path, monkeypatch):
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    chiamate = {}
    monkeypatch.setattr(render.montaggio, "monta", lambda cartella, **kw: chiamate.update(kw))
    render.render(tmp_path, tl, formato="orizzontale")
    assert chiamate["cornice"] == "cornice-16x9.png" and chiamate["formato"] == "orizzontale"
    assert cornici == [("Uno", "verde-smeraldo")]
    assert "PlayResX: 1920\nPlayResY: 1080" in (tmp_path / "sub.ass").read_text(encoding="utf-8")


def test_render_chip_dello_scenario_rifa_la_cornice(tmp_path, monkeypatch):
    cornici = []
    tl = _setup(tmp_path, monkeypatch, cornici)
    render.render(tmp_path, tl)
    tl["chip"] = "PROVA GRATIS 30 GIORNI"
    render.render(tmp_path, tl)
    assert cornici == [("Uno", "verde-smeraldo"), ("Uno", "verde-smeraldo", "PROVA GRATIS 30 GIORNI")]
