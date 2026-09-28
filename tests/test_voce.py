from voce import cue, frasi, parse_silencedetect, srt

STDERR = """
[silencedetect @ 0x1] silence_start: 2.10
[silencedetect @ 0x1] silence_end: 2.60 | silence_duration: 0.50
[silencedetect @ 0x1] silence_start: 3.00
[silencedetect @ 0x1] silence_end: 3.10 | silence_duration: 0.10
[silencedetect @ 0x1] silence_start: 5.00
[silencedetect @ 0x1] silence_end: 5.70 | silence_duration: 0.70
"""


def test_frasi_spezza_su_punteggiatura_finale():
    assert frasi("Hai presente? Ecco. Con Acme va da sola! Link in bio.") == [
        "Hai presente?", "Ecco.", "Con Acme va da sola!", "Link in bio."]


def test_frasi_tiene_ultimo_frammento_senza_punto():
    assert frasi("Hai presente? Ecco. Link in bio") == [
        "Hai presente?", "Ecco.", "Link in bio"]


def test_parse_silencedetect():
    assert parse_silencedetect(STDERR) == [(2.10, 2.60), (3.00, 3.10), (5.00, 5.70)]


def test_cue_usa_i_silenzi_piu_lunghi_come_confini():
    c = cue(["A.", "B.", "C."], parse_silencedetect(STDERR), durata=8.0)
    # 2 confini = i 2 silenzi più lunghi (0.70 e 0.50), in ordine di tempo, al punto medio
    assert c == [(0.0, 2.35, "A."), (2.35, 5.35, "B."), (5.35, 8.0, "C.")]


def test_cue_senza_silenzi_sufficienti_divide_in_proporzione():
    c = cue(["AA.", "B."], [], durata=3.0)
    assert c[0][0] == 0.0 and c[-1][1] == 3.0 and c[0][1] == c[1][0]


def test_srt_formato():
    assert srt([(0.0, 1.5, "Ciao."), (1.5, 62.25, "Fine.")]) == (
        "1\n00:00:00,000 --> 00:00:01,500\nCiao.\n\n"
        "2\n00:00:01,500 --> 00:01:02,250\nFine.\n")


def test_prompt_tts_stile_come_tag_prima_del_testo():
    from voce import prompt_tts
    p = prompt_tts("Hai presente?\n Ecco.")
    assert p.startswith("[") and p.endswith("] Hai presente? Ecco.")
    assert "\n" not in p


def test_inizia_con_ignora_punteggiatura_e_maiuscole():
    from voce import inizia_con
    assert inizia_con("hai presente quando un'agenzia ti chiede", "Hai presente, quando un'agenzia ti chiede il preventivo")
    assert not inizia_con("Leggi in italiano con tono colloquiale. Hai presente", "Hai presente quando un'agenzia")


def test_cue_sceglie_la_pausa_piu_vicina_alla_stima_non_la_piu_lunga():
    from voce import cue
    # frase 1 corta: stima confine ~2s; c'e' una pausa lunga a 6.5s dentro la frase 2 da ignorare
    silenzi = [(1.9, 2.2), (6.0, 7.0), (9.4, 9.6)]
    c = cue(["Ecco.", "Una frase molto piu lunga di prima.", "Fine della storia qui."], silenzi, durata=13.0)
    assert c[0][1] == 2.05
    assert c[1][1] == 9.5


def test_spezza_cue_in_pezzi_brevi_con_tempi_proporzionali():
    from voce import spezza
    cues = [(0.0, 6.0, "Hai presente quando un'agenzia ti chiede il preventivo per un gruppo?")]
    pezzi = spezza(cues, max_parole=5)
    assert all(len(t.split()) <= 5 for _, _, t in pezzi)
    assert pezzi[0][0] == 0.0 and pezzi[-1][1] == 6.0
    assert all(a[1] == b[0] for a, b in zip(pezzi, pezzi[1:]))          # contigui, senza sovrapposizioni
    assert " ".join(t for _, _, t in pezzi) == cues[0][2]


def test_ass_ha_risoluzione_verticale_e_niente_box():
    from voce import ass
    s = ass([(0.0, 1.5, "Ciao a tutti"), (1.5, 62.25, "Fine")])
    assert "PlayResX: 1080" in s and "PlayResY: 1920" in s
    assert "Dialogue: 0,0:00:00.00,0:00:01.50,Reel,,0,0,0,,Ciao a tutti" in s
    assert "0:01:02.25" in s
    stile = next(r for r in s.splitlines() if r.startswith("Style: Reel"))
    assert stile.split(",")[15] == "1"                                 # BorderStyle 1: contorno, non box


def test_spezza_preferisce_le_virgole():
    from voce import spezza
    pezzi = spezza([(0.0, 4.0, "Hai presente il gruppo grande, dove l'accordo con l'agenzia è una gratuità ogni venti?")],
                   max_parole=5)
    assert pezzi[0][2] == "Hai presente il gruppo grande,"


import pytest


TESTO_CONTRATTO = (
    "Hai presente il contratto da stampare, firmare a penna e scansionare? "
    "Ecco. Su Acme lo generi dall'ordine con un clic, e lo mandi in firma. "
    "Il cliente firma dal telefono con un codice OTP, e il contratto torna in pratica già firmato. "
    "Trenta giorni di prova, gratis. Link in bio."
)


def test_pezzi_testo_come_i_sottotitoli():
    from voce import pezzi_testo
    p = pezzi_testo(TESTO_CONTRATTO)
    assert "e lo mandi in firma." in p
    assert all(len(x.split()) <= 5 for x in p)


def test_trova_battuta_prefisso_maiuscole_e_punteggiatura():
    from voce import trova_battuta
    pezzi = [(0.0, 1.5, "Hai presente il contratto"), (7.3, 8.7, "Su Acme lo generi"),
             (8.7, 10.2, "dall'ordine con un clic,")]
    assert trova_battuta("su acme, lo generi", pezzi) == 7.3


def test_trova_battuta_a_cavallo_di_due_pezzi():
    from voce import trova_battuta
    pezzi = [(14.7, 16.0, "e il contratto torna"), (16.0, 17.6, "in pratica già firmato.")]
    assert trova_battuta("e il contratto torna in pratica", pezzi) == 14.7


def test_trova_battuta_inesistente_elenca_i_pezzi():
    from voce import trova_battuta
    with pytest.raises(ValueError, match="Hai presente"):
        trova_battuta("questa frase non c'e'", [(0.0, 1.0, "Hai presente il contratto")])
    with pytest.raises(ValueError):
        trova_battuta("  ", [(0.0, 1.0, "Hai presente il contratto")])


def test_voce_attuale_dipende_solo_dal_testo(tmp_path):
    from voce import segna_voce, voce_attuale
    assert not voce_attuale(tmp_path, "Ciao.")
    (tmp_path / "voce.wav").write_bytes(b"x")
    segna_voce(tmp_path, "Ciao.")
    assert voce_attuale(tmp_path, "Ciao.")
    assert voce_attuale(tmp_path, "  Ciao. ")        # spazi non contano
    assert not voce_attuale(tmp_path, "Ciao a tutti.")


def test_ass_contorno_di_default_e_personalizzato():
    from voce import ass
    assert ",&H00313D2A," in ass([])                       # verde di oggi (#2a3d31 in BGR)
    assert ",&H0050351B," in ass([], contorno="#1b3550")


def test_ass_usa_la_famiglia_extrabold_di_font_sub():
    from pathlib import Path
    from voce import ass
    assert "Style: Reel,Plus Jakarta Sans ExtraBold,70," in ass([])
    # il nome deve combaciare con la famiglia (nameID 1) del file che render copia come font-sub.ttf
    dati = (Path(__file__).resolve().parent.parent / "assets" / "PlusJakartaSans-ExtraBold.ttf").read_bytes()
    assert "Plus Jakarta Sans ExtraBold".encode("utf-16-be") in dati
