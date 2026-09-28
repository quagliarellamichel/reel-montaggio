"""Test suite for capture.py — login, registrazione scenario."""
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

import capture
from capture import SENSIBILI_DEFAULT, css_blur, main


def _no_op(*a, **kw):
    raise AssertionError("non doveva essere chiamato")


def test_css_blur_include_default_e_scenario():
    css = css_blur(["#cliente-nome"])
    assert "#cliente-nome" in css and "filter: blur(" in css
    for s in SENSIBILI_DEFAULT:
        assert s in css


def test_css_blur_lista_vuota_usa_solo_default():
    assert css_blur([]).count("{") == 1


def test_main_rifiuta_slug_non_valido(monkeypatch, capsys):
    """Malicious slug 'x; rm -rf /' should be rejected before registra is called."""
    monkeypatch.setattr(sys, "argv", ["capture.py", "registra", "x; rm -rf /"])
    with patch("capture.registra") as mock_registra:
        result = main()
        assert result == 2
        mock_registra.assert_not_called()
    captured = capsys.readouterr()
    assert "slug non valido" in captured.out


def test_registra_richiede_gemini_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "AUTH", tmp_path / ".auth.json")
    (tmp_path / ".auth.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(capture.importlib, "import_module", _no_op)

    with pytest.raises(SystemExit, match="GEMINI_API_KEY"):
        capture.registra("demo")


def test_valida_battute_prima_di_aprire_il_browser(tmp_path):
    f = tmp_path / "s.py"
    f.write_text('def scena(page, reel):\n    reel.battuta("Su Acme lo generi")\n', encoding="utf-8")
    testo = "Hai presente il contratto? Ecco. Su Acme lo generi dall'ordine. Link in bio."
    assert capture.valida_battute(f, testo) == ["Su Acme lo generi"]
    f.write_text('def scena(page, reel):\n    reel.battuta("frase che non c e")\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Battuta non trovata"):
        capture.valida_battute(f, testo)


# pezzi di TESTO_ORDINE (voce.pezzi_testo), indici 0-13:
# 0 'Hai presente il' | 1 'contratto da stampare,' | 2 'firmare a penna e scansionare?' | 3 'Ecco.'
# 4 'Su Acme lo generi' | 5 "dall'ordine con un clic," | 6 'e lo mandi in firma.'
# 7 'Il cliente firma dal telefono' | 8 'con un codice OTP,' | 9 'e il contratto torna'
# 10 'in pratica gia firmato.' | 11 'Trenta giorni di prova,' | 12 'gratis.' | 13 'Link in bio.'
TESTO_ORDINE = (
    "Hai presente il contratto da stampare, firmare a penna e scansionare? "
    "Ecco. Su Acme lo generi dall'ordine con un clic, e lo mandi in firma. "
    "Il cliente firma dal telefono con un codice OTP, e il contratto torna in pratica già firmato. "
    "Trenta giorni di prova, gratis. Link in bio."
)


def _scenario(tmp_path, *battute):
    f = tmp_path / "s.py"
    righe = "".join(f'    reel.battuta({b!r})\n' for b in battute)
    f.write_text(f"def scena(page, reel):\n{righe}", encoding="utf-8")
    return f


def test_valida_battute_indici_crescenti_e_fuori_dal_primo_pezzo_passa(tmp_path):
    f = _scenario(tmp_path, "Su Acme lo generi", "e lo mandi in firma", "Trenta giorni di prova")
    assert capture.valida_battute(f, TESTO_ORDINE) == [
        "Su Acme lo generi", "e lo mandi in firma", "Trenta giorni di prova"]


def test_valida_battute_fuori_ordine_solleva_prima_del_browser(tmp_path):
    # "e lo mandi in firma" (pezzo 6) viene prima di "Su Acme lo generi" (pezzo 4): indici
    # non crescenti, esattamente cio' che timeline.tratti rifiuterebbe solo dopo la registrazione.
    f = _scenario(tmp_path, "e lo mandi in firma", "Su Acme lo generi")
    with pytest.raises(ValueError, match="fuori ordine"):
        capture.valida_battute(f, TESTO_ORDINE)


def test_valida_battute_sul_primo_pezzo_solleva(tmp_path):
    # "Hai presente il" e' il pezzo 0 (tempo 0 della voce): timeline.tratti lo rifiuta sempre
    # (v=0 con c>0), quindi il pre-flight deve fermarsi qui, non al render.
    f = _scenario(tmp_path, "Hai presente il contratto")
    with pytest.raises(ValueError, match="primo pezzo"):
        capture.valida_battute(f, TESTO_ORDINE)


def test_main_accetta_voce_e_opzione_voce_nuova(monkeypatch):
    chiamate = []
    monkeypatch.setattr(capture, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(capture, "registra", lambda slug, voce_nuova=False, palette_forzata=None: chiamate.append(("r", slug, voce_nuova)))
    monkeypatch.setattr(capture, "rivoce", lambda slug: chiamate.append(("v", slug)))
    monkeypatch.setattr(sys, "argv", ["capture.py", "registra", "contratto-firma-otp", "--voce-nuova"])
    assert main() == 0
    monkeypatch.setattr(sys, "argv", ["capture.py", "voce", "contratto-firma-otp"])
    assert main() == 0
    assert chiamate == [("r", "contratto-firma-otp", True), ("v", "contratto-firma-otp")]


def test_scegli_palette_rotazione_e_forzata(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "BASE", tmp_path)
    (tmp_path / "reels.md").write_text(
        "## A\n- stato: pubblicato\n- video: https://x/a.mp4\n- palette: verde-smeraldo\n- caption:\n  > a\n",
        encoding="utf-8")
    assert capture.scegli_palette(types.SimpleNamespace())["nome"] == "blu-mare"
    assert capture.scegli_palette(types.SimpleNamespace(PALETTE="terracotta"))["nome"] == "terracotta"
    with pytest.raises(ValueError, match="inesistente"):
        capture.scegli_palette(types.SimpleNamespace(PALETTE="rosa"))
    # --palette da riga di comando vince anche su PALETTE dello scenario
    assert capture.scegli_palette(types.SimpleNamespace(PALETTE="terracotta"), "viola-sera")["nome"] == "viola-sera"


def test_main_registra_passa_palette_forzata(monkeypatch):
    chiamate = []
    monkeypatch.setattr(capture, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(capture, "registra", lambda slug, voce_nuova=False, palette_forzata=None:
                        chiamate.append((slug, voce_nuova, palette_forzata)))
    monkeypatch.setattr(sys, "argv", ["capture.py", "registra", "prova", "--palette", "blu-mare"])
    assert main() == 0
    monkeypatch.setattr(sys, "argv", ["capture.py", "registra", "prova", "--voce-nuova"])
    assert main() == 0
    assert chiamate == [("prova", False, "blu-mare"), ("prova", True, None)]

