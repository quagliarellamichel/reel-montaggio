"""Contratto di uno scenario. Copiare in scenari/<slug>.py e adattare al proprio sito."""
TITOLO = "Titolo del reel"
HOOK = "Il cliente vuole il preventivo\ndel gruppo. Adesso."
TESTO = "Testo letto dalla voce, registro collega, 20-40 secondi. Trenta giorni di prova, gratis."
CAPTION = "Caption 2-4 righe.\n\n#agenziediviaggio #touroperator #turismo"
SENSIBILI: list[str] = []


def scena(page, reel) -> None:
    """reel.punta(el, zoom=1.8, lento=1.2) indica un elemento (anello + cursore) e ci porta la telecamera;
    reel.fuoco(el) muove solo la telecamera; `with reel.taglio():` toglie un'attesa dal video;
    reel.battuta("inizio di una frase del TESTO") aggancia il video alla voce da quel punto;
    reel.card(titolo, [(voce, valore)], nota) e' il riquadro finale; reel.dopo(fn) pulisce a fine scena;
    reel.otp_email("oggetto", invia=lambda: bottone.click()) legge un OTP via IMAP (SOCIAL_MAIL_*)."""
    page.goto(page.url.rstrip("/") + "/ordini")
    reel.punta("table", zoom=1.35)
    page.wait_for_timeout(1500)
