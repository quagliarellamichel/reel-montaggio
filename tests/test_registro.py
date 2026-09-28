from registro import leggi, prossimo, segna_pubblicato, segna_errore, nuova_sezione

BASE = (
    "# Reel Instagram — registro\n\nintro\n\n"
    + nuova_sezione("Uno", "https://x/1.mp4", "Prima riga con \"virgolette\" #tag\n\nDopo riga vuota 🎉")
    + nuova_sezione("Due", "https://x/2.mp4", "Caption due")
)


def test_leggi_estrae_sezioni_e_caption_multilinea():
    reels = leggi(BASE)
    assert [r.titolo for r in reels] == ["Uno", "Due"]
    assert reels[0].stato == "in-coda"
    assert reels[0].video == "https://x/1.mp4"
    assert reels[0].caption == "Prima riga con \"virgolette\" #tag\n\nDopo riga vuota 🎉"


def test_prossimo_salta_pubblicati():
    reels = leggi(BASE)
    testo = segna_pubblicato(BASE, reels[0], "2026-10-04", "https://instagram.com/reel/abc")
    assert prossimo(leggi(testo)).titolo == "Due"


def test_prossimo_none_se_coda_vuota():
    assert prossimo(leggi("# Reel Instagram — registro\n")) is None


def test_segna_pubblicato_non_tocca_altre_sezioni():
    reels = leggi(BASE)
    testo = segna_pubblicato(BASE, reels[0], "2026-10-04", "https://instagram.com/reel/abc")
    dopo = leggi(testo)
    assert dopo[0].stato == "pubblicato"
    assert "- pubblicato: 2026-10-04 · https://instagram.com/reel/abc" in testo
    assert dopo[0].caption == reels[0].caption
    assert testo.split("## Due", 1)[1] == BASE.split("## Due", 1)[1]


def test_segna_errore_scrive_motivo_su_una_riga():
    reels = leggi(BASE)
    testo = segna_errore(BASE, reels[1], "container ERROR:\nvideo troppo lungo")
    r = leggi(testo)[1]
    assert r.stato == "errore"
    assert "- errore: container ERROR: video troppo lungo" in testo


def test_caption_multilinea_roundtrip():
    reels = leggi(BASE)
    testo = segna_errore(BASE, reels[0], "x")
    assert leggi(testo)[0].caption == reels[0].caption


def test_segna_pubblicato_permalink_con_newline_non_spezza_registro():
    reels = leggi(BASE)
    motivo = "media id M1 (permalink non disponibile: riga1\n## finta\nriga3)"
    testo = segna_pubblicato(BASE, reels[0], "2026-10-04", motivo)
    sezioni = leggi(testo)
    assert len(sezioni) == 2
    righe = testo.split("\n")
    pubblicato = [r for r in righe if r.startswith("- pubblicato:")]
    assert len(pubblicato) == 1
    assert not any(r.startswith("## finta") for r in righe)


def test_nuova_sezione_con_palette_e_rilettura():
    s = nuova_sezione("T", "https://x/v.mp4", "riga", palette="blu-mare")
    assert "- video: https://x/v.mp4\n- palette: blu-mare\n- caption:" in s
    r = leggi(s)[0]
    assert (r.palette, r.caption, r.video, r.stato) == ("blu-mare", "riga", "https://x/v.mp4", "in-coda")


def test_nuova_sezione_senza_palette_invariata():
    assert nuova_sezione("T", "v", "c") == "## T\n- stato: in-coda\n- video: v\n- caption:\n  > c\n\n"


def _reg_pubblicati() -> str:
    t = "# Reel\n\n" + nuova_sezione("A", "https://x/a.mp4", "Cap A") + nuova_sezione("B", "https://x/b.mp4", "Cap B")
    t = segna_pubblicato(t, leggi(t)[0], "2026-09-25", "https://ig/a")
    return t


def test_prossimo_youtube_solo_pubblicati_senza_riga():
    from registro import prossimo_youtube, segna_youtube
    t = _reg_pubblicati()
    assert prossimo_youtube(leggi(t)).titolo == "A"   # B è in-coda: non ancora su IG
    t = segna_youtube(t, leggi(t)[0], "salta")
    assert prossimo_youtube(leggi(t)) is None


def test_segna_youtube_non_cambia_stato_e_appiattisce():
    from registro import prossimo_youtube, segna_youtube
    t = _reg_pubblicati()
    t2 = segna_youtube(t, leggi(t)[0], "errore: boom\n## rotto")
    a, b = leggi(t2)
    assert a.stato == "pubblicato" and a.youtube == "errore: boom ## rotto"
    assert b.titolo == "B" and b.youtube == ""
    assert "- pubblicato: 2026-09-25 · https://ig/a" in t2
