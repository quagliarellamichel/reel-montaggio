from email.message import EmailMessage

import pytest

import kit


class Loc:
    def __init__(self, bb):
        self.first = self
        self._bb = bb

    def bounding_box(self):
        return self._bb


class FakePage:
    def __init__(self, bb=None):
        self.valutati = []
        self._bb = bb or {"x": 100, "y": 200, "width": 50, "height": 20}

    def evaluate(self, js, arg=None):
        self.valutati.append((js, arg))

    def wait_for_timeout(self, ms):
        pass

    def locator(self, sel):
        return Loc(self._bb)


def test_eventi_e_marcatore_alternato():
    p = FakePage()
    r = kit.Reel(p)
    r.inizio()
    r.fuoco("#x", dx=5, dy=-10)
    r.battuta("Su Acme")
    assert [e[0] for e in r.eventi] == ["inizio", "fuoco", "battuta"]
    assert r.eventi[1][2] == (130, 200, 0, None)
    colori = [a for js, a in p.valutati if "__rmDraw" in js]
    assert colori == ["#0000ff", "#ff0000", "#0000ff"]


def test_fuoco_senza_bounding_box_non_registra():
    p = FakePage()
    p.locator = lambda sel: Loc(None)
    r = kit.Reel(p)
    r.fuoco("#nascosto")
    assert r.eventi == []


def test_taglio_chiude_anche_su_eccezione():
    r = kit.Reel(FakePage())
    with pytest.raises(RuntimeError):
        with r.taglio():
            raise RuntimeError("attesa scaduta")
    assert [e[0] for e in r.eventi] == ["taglio_da", "taglio_a"]


def test_pulizie_in_ordine_inverso_anche_se_una_fallisce(capsys):
    r = kit.Reel(FakePage())
    fatte = []
    r.dopo(lambda: fatte.append(1))
    r.dopo(lambda: 1 / 0)
    r.dopo(lambda: fatte.append(3))
    r.pulisci()
    assert fatte == [3, 1]
    assert "pulizia fallita" in capsys.readouterr().out


def test_esegui_scena_pulisce_e_propaga_l_errore():
    r = kit.Reel(FakePage())
    fatte = []

    class Sc:
        @staticmethod
        def scena(page, reel):
            reel.dopo(lambda: fatte.append("pulito"))
            raise RuntimeError("scena rotta")

    with pytest.raises(RuntimeError, match="scena rotta"):
        kit.esegui_scena(Sc, r.page, r)
    assert fatte == ["pulito"]


def test_card_passa_titolo_righe_nota_colori_e_mette_il_fuoco():
    p = FakePage()
    r = kit.Reel(p)
    r.card("CONTRATTO ASTOI", [("Firmato con OTP", "✓")], nota="Zero carta")
    js, arg = next((js, a) for js, a in p.valutati if "reel-card" in js)
    assert arg == ["CONTRATTO ASTOI", [["Firmato con OTP", "✓"]], "Zero carta",
                   {"fondo": "#2a3331", "valore": "#3ddc84", "nota": "#f5c400"}]
    assert r.eventi[-1][0] == "fuoco"


def test_card_usa_i_colori_della_palette():
    import palette
    p = FakePage()
    r = kit.Reel(p, palette=palette.per_nome("blu-mare"))
    r.card("X", [("a", "b")])
    _, arg = next((js, a) for js, a in p.valutati if "reel-card" in js)
    assert arg[3] == {"fondo": "#1f2f3d", "valore": "#6cc4ff", "nota": "#ffd166"}


def test_battute_scenario_legge_i_letterali(tmp_path):
    f = tmp_path / "s.py"
    f.write_text('def scena(page, reel):\n    reel.battuta("Su Acme lo generi")\n'
                 '    x = "no"\n    reel.battuta("e lo mandi in firma")\n', encoding="utf-8")
    assert kit.battute_scenario(f) == ["Su Acme lo generi", "e lo mandi in firma"]


def test_battute_scenario_ordine_sorgente_non_bfs(tmp_path):
    """ast.walk e' BFS: una battuta annidata (dentro un 'with') e' piu' profonda nell'albero di una
    battuta top-level successiva, quindi il BFS la scoprirebbe dopo anche se viene prima nel file.
    battute_scenario deve restituire l'ordine del sorgente (riga, colonna), non l'ordine di visita."""
    f = tmp_path / "s.py"
    f.write_text(
        'def scena(page, reel):\n'
        '    with reel.taglio():\n'
        '        reel.battuta("annidata nel with")\n'
        '    reel.battuta("top level dopo")\n',
        encoding="utf-8")
    assert kit.battute_scenario(f) == ["annidata nel with", "top level dopo"]


class FakeImap:
    casella: dict = {}

    def __init__(self, host, port):
        pass

    def login(self, u, p):
        pass

    def select(self, box):
        return "OK", [b""]

    def search(self, charset, crit):
        return "OK", [b" ".join(str(i).encode() for i in sorted(self.casella))]

    def fetch(self, i, what):
        return "OK", [(b"", self.casella[int(i)])]

    def logout(self):
        pass


def _mail(soggetto, corpo):
    m = EmailMessage()
    m["Subject"] = soggetto
    m.set_content(corpo)
    return m.as_bytes()


def test_otp_email_legge_solo_le_email_nuove(monkeypatch):
    FakeImap.casella = {1: _mail("eSignature OTP", "Vecchio codice 11111")}
    monkeypatch.setattr(kit.imaplib, "IMAP4_SSL", FakeImap)
    monkeypatch.setattr(kit.time, "sleep", lambda s: None)
    monkeypatch.setenv("SOCIAL_MAIL_HOST", "h")
    monkeypatch.setenv("SOCIAL_MAIL", "x@y")
    monkeypatch.setenv("SOCIAL_MAIL_PASSWORD", "p")

    def invia():
        FakeImap.casella[2] = _mail("Newsletter", "sconto 20261")
        FakeImap.casella[3] = _mail("eSignature OTP", "Il tuo codice: 57043")

    assert kit.Reel(FakePage()).otp_email("otp", invia) == "57043"


def test_otp_email_timeout_errore(monkeypatch):
    FakeImap.casella = {}
    monkeypatch.setattr(kit.imaplib, "IMAP4_SSL", FakeImap)
    monkeypatch.setattr(kit.time, "sleep", lambda s: None)
    orologio = iter(range(0, 1000, 10))
    monkeypatch.setattr(kit.time, "monotonic", lambda: next(orologio))
    monkeypatch.setenv("SOCIAL_MAIL_HOST", "h")
    monkeypatch.setenv("SOCIAL_MAIL", "x@y")
    monkeypatch.setenv("SOCIAL_MAIL_PASSWORD", "p")
    with pytest.raises(RuntimeError, match="OTP non arrivato"):
        kit.Reel.__new__(kit.Reel).otp_email("otp", lambda: None, timeout=30)


def test_fuoco_lento_registra_la_durata_del_pan():
    p = FakePage()
    p.locator = lambda sel: Loc({"x": 0, "y": 0, "width": 100, "height": 50})
    r = kit.Reel(p)
    r.fuoco("#a")
    r.fuoco("#a", dx=10, lento=5)
    assert r.eventi[0][2] == (50, 25, 0, None) and r.eventi[1][2] == (60, 25, 5, None)


def test_punta_disegna_anello_e_cursore_poi_mette_il_fuoco():
    p = FakePage({"x": 100, "y": 200, "width": 50, "height": 20})
    r = kit.Reel(p, palette={"accento": "#4db6ff", "card_fondo": "#000", "card_valore": "#fff", "card_nota": "#ff0"})
    r.punta("#bottone", zoom=1.8, lento=1.2)
    js, arg = next((js, a) for js, a in p.valutati if "__rr" in js)
    assert arg == [{"x": 100, "y": 200, "width": 50, "height": 20}, "#4db6ff"]
    assert r.eventi[-1][0] == "fuoco" and r.eventi[-1][2] == (125, 210, 1.2, 1.8)


def test_card_toglie_il_puntatore():
    p = FakePage()
    r = kit.Reel(p)
    r.punta("#x")
    r.card("T", [("a", "b")])
    assert any("__rr" in js and "remove" in js for js, _ in p.valutati)


def test_fuoco_zoom_fuori_range_rifiutato():
    with pytest.raises(ValueError):
        kit.Reel(FakePage()).fuoco("#x", zoom=0.8)


def test_fuoco_fuori_schermo_avvisa(capsys):
    p = FakePage({"x": 800, "y": 1100, "width": 50, "height": 20})
    kit.Reel(p).fuoco("#sotto")
    assert "fuori schermo" in capsys.readouterr().out


def test_esegui_scena_segna_fine_solo_se_ci_sono_pulizie():
    class Sc:
        @staticmethod
        def scena(page, reel):
            reel.dopo(lambda: None)
    r = kit.Reel(FakePage())
    kit.esegui_scena(Sc, r.page, r)
    assert r.eventi[-1][0] == "fine"
    r2 = kit.Reel(FakePage())
    kit.esegui_scena(type("S", (), {"scena": staticmethod(lambda p, r: None)}), r2.page, r2)
    assert r2.eventi == []
