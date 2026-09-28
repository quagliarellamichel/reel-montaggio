"""Kit degli scenari dei reel: scena(page, reel) riceve un Reel. Ogni evento (fuoco, taglio,
battuta) cambia colore al marcatore di sincronia, cosi' il montaggio ne legge il tempo vero dal
video (vedi montaggio.MARCATORE_PX)."""
from __future__ import annotations

import ast
import contextlib
import email
import imaplib
import os
import re
import time
from email.header import decode_header, make_header
from pathlib import Path

# Riquadro finale unico per tutti i reel: colori dalla palette del reel
CARD_JS = r"""([titolo, righe, nota, c]) => {
  document.getElementById('reel-card')?.remove();
  document.getElementById('reel-card-velo')?.remove();
  const esc = s => String(s).replace(/[&<>]/g, x => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[x]));
  // velo scuro sulla pagina: la card e' l'unica cosa da guardare
  const velo = document.createElement('div');
  velo.id = 'reel-card-velo';
  velo.style.cssText = 'position:fixed;inset:0;z-index:99998;background:rgba(10,14,13,0);transition:background .5s';
  document.body.appendChild(velo);
  const card = document.createElement('div');
  card.id = 'reel-card';
  card.style.cssText = 'position:fixed;left:50%;top:50%;transform:translate(-50%,-50%) scale(.94);opacity:0;z-index:99999;' +
    `width:540px;background:linear-gradient(160deg,${c.fondo} 0%,color-mix(in srgb,${c.fondo} 78%,#000) 100%);` +
    'color:#fff;border-radius:26px;padding:26px 30px 24px;font:700 27px/1.2 "Plus Jakarta Sans",sans-serif;' +
    `box-shadow:0 34px 90px rgba(0,0,0,.55),0 0 0 1px rgba(255,255,255,.08),0 0 60px ${c.valore}33;` +
    'transition:transform .45s cubic-bezier(.2,.7,.2,1),opacity .45s';
  card.innerHTML =
    `<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px">` +
      `<span style="width:10px;height:10px;border-radius:50%;background:${c.valore};box-shadow:0 0 14px ${c.valore}"></span>` +
      `<span style="font-size:15px;letter-spacing:3px;color:${c.valore}">${esc(titolo)}</span></div>` +
    righe.map(([k, v], i) => `<div class="reel-riga" style="display:flex;justify-content:space-between;align-items:center;gap:14px;` +
      `padding:11px 0;border-top:1px solid rgba(255,255,255,.09);opacity:0;transform:translateX(-10px);` +
      `transition:opacity .4s ${.25 + i * .14}s,transform .4s ${.25 + i * .14}s">` +
      `<span>${esc(k)}</span><b style="display:inline-flex;align-items:center;justify-content:center;min-width:36px;height:36px;` +
      `padding:0 10px;border-radius:999px;background:${c.valore};color:${c.fondo};font-size:22px">${esc(v)}</b></div>`).join('') +
    (nota ? `<div style="margin-top:16px;padding-top:14px;border-top:1px solid rgba(255,255,255,.09);font-size:22px;color:${c.nota}">${esc(nota)}</div>` : '');
  document.body.appendChild(card);
  void card.offsetWidth;   // stato iniziale applicato: l'entrata parte da qui
  velo.style.background = 'rgba(10,14,13,.45)';
  card.style.transform = 'translate(-50%,-50%) scale(1)';
  card.style.opacity = '1';
  card.querySelectorAll('.reel-riga').forEach(r => { r.style.opacity = '1'; r.style.transform = 'none'; });
}"""

# Colori della card senza palette (verde-smeraldo)
CARD_DEFAULT = {"fondo": "#2a3331", "valore": "#3ddc84", "nota": "#f5c400"}

# Puntatore: anello del colore d'accento attorno al bersaglio + cursore che ci scivola sopra
# (transizioni CSS, finiscono nel girato). Il cursore nasce spostato e arriva sul bersaglio: il
# primo movimento si vede. Un solo anello e un solo cursore per documento; una navigazione li toglie.
PUNTATORE_JS = r"""([bb, c]) => {
  const curva = 'cubic-bezier(.2,.7,.2,1)';
  let r = document.getElementById('__rr'), p = document.getElementById('__rp');
  if (!r) {
    r = document.createElement('div'); r.id = '__rr';
    r.style.cssText = 'position:fixed;z-index:2147483646;pointer-events:none;border-radius:10px;opacity:0;' +
      `transition:left .8s ${curva},top .8s ${curva},width .8s ${curva},height .8s ${curva},opacity .4s`;
    document.body.appendChild(r);
    p = document.createElement('div'); p.id = '__rp';
    p.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483646;pointer-events:none;width:34px;height:34px;' +
      `transform:translate(${bb.x + bb.width / 2 + 260}px,${bb.y + bb.height / 2 + 180}px);transition:transform .9s ${curva}`;
    p.innerHTML = '<svg viewBox="0 0 24 24" width="34" height="34"><path d="M5 3l14 8-6 1.5L9 20z" fill="#fff" ' +
      'stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.body.appendChild(p);
    void p.offsetWidth;
  }
  const m = 7;
  Object.assign(r.style, { left: (bb.x - m) + 'px', top: (bb.y - m) + 'px', width: (bb.width + 2 * m) + 'px',
    height: (bb.height + 2 * m) + 'px', border: '3px solid ' + c,
    boxShadow: '0 0 0 3px ' + c + '55, 0 0 26px ' + c + '99', opacity: '1' });
  p.style.transform = `translate(${bb.x + bb.width / 2 - 7}px,${bb.y + bb.height / 2 - 4}px)`;
}"""
SPUNTA_JS = "() => { document.getElementById('__rr')?.remove(); document.getElementById('__rp')?.remove(); }"


class Reel:
    def __init__(self, page, colori=("#ff0000", "#0000ff"), pausa_ms: int = 120, palette: dict | None = None):
        self.page = page
        self.t0 = time.monotonic()
        self.eventi: list[tuple[str, float, object]] = []
        self.colore = colori[0]
        self._colori = colori
        self._pausa = pausa_ms
        self._pulizie = []
        self._card = ({"fondo": palette["card_fondo"], "valore": palette["card_valore"], "nota": palette["card_nota"]}
                      if palette else dict(CARD_DEFAULT))
        self._accento = palette["accento"] if palette else CARD_DEFAULT["valore"]

    def _segna(self, tipo: str, dati=None) -> None:
        self.eventi.append((tipo, round(time.monotonic() - self.t0, 2), dati))
        self.colore = self._colori[len(self.eventi) % 2]
        self.page.evaluate("c => window.__rmDraw && window.__rmDraw(c)", self.colore)
        self.page.wait_for_timeout(self._pausa)   # almeno un frame col colore nuovo

    def inizio(self) -> None:
        """Da qui parte il reel: la home prima dello scenario viene tagliata."""
        self._segna("inizio")

    def fuoco(self, bersaglio, dx: float = 0, dy: float = 0, lento: float = 0, zoom: float | None = None) -> None:
        """Telecamera sul centro dell'elemento (selettore o Locator) + (dx, dy), da adesso.
        `lento`: secondi di pan per arrivarci (deriva), invece della transizione standard.
        `zoom`: zoom proprio di questo fuoco (stretto su un bottone, largo su una griglia)."""
        if zoom is not None and not 1 <= zoom <= 3:
            raise ValueError(f"zoom {zoom} fuori da 1-3")   # subito, non a fine registrazione in ffmpeg
        loc = self.page.locator(bersaglio) if isinstance(bersaglio, str) else bersaglio
        bb = loc.first.bounding_box()
        if bb:
            x, y = bb["x"] + bb["width"] / 2 + dx, bb["y"] + bb["height"] / 2 + dy
            if not (0 <= x <= 1920 and 0 <= y <= 1080):
                # coordinate del viewport: sotto la piega la camera si ferma al bordo e l'anello non si vede
                print(f"ATTENZIONE fuoco fuori schermo ({x:.0f},{y:.0f}): scorrere la pagina prima (dentro un taglio)")
            self._segna("fuoco", (x, y, lento, zoom))

    def punta(self, bersaglio, dx: float = 0, dy: float = 0, lento: float = 0, zoom: float | None = None) -> None:
        """Indica un elemento: anello d'accento attorno e cursore che ci scivola sopra, poi la
        telecamera lo segue. E' quello che rende leggibile COSA si sta guardando."""
        loc = self.page.locator(bersaglio) if isinstance(bersaglio, str) else bersaglio
        bb = loc.first.bounding_box()
        if bb:
            self.page.evaluate(PUNTATORE_JS, [bb, self._accento])
            self.fuoco(loc, dx, dy, lento, zoom)

    def spunta(self) -> None:
        """Toglie anello e cursore (prima della card finale, o quando non c'e' piu' un bersaglio)."""
        self.page.evaluate(SPUNTA_JS)

    @contextlib.contextmanager
    def taglio(self):
        """Il blocco viene tolto dal reel (attese lunghe); chiuso anche se il blocco fallisce."""
        self._segna("taglio_da")
        try:
            yield
        finally:
            self._segna("taglio_a")

    def battuta(self, testo: str) -> None:
        """Da qui il video va a tempo con questo punto del TESTO (inizio di un pezzo di sottotitolo)."""
        self._segna("battuta", testo)

    def card(self, titolo: str, righe, nota: str | None = None) -> None:
        self.spunta()
        self.page.evaluate(CARD_JS, [titolo, [list(r) for r in righe], nota, self._card])
        self.fuoco("#reel-card")

    def dopo(self, fn) -> None:
        """Pulizia a fine scena (listino creato, chiave API...): eseguita anche se la scena fallisce."""
        self._pulizie.append(fn)

    def pulisci(self) -> None:
        for fn in reversed(self._pulizie):
            try:
                fn()
            except Exception as e:  # una pulizia rotta non deve saltare le altre
                print(f"pulizia fallita: {e}")
        self._pulizie = []

    @staticmethod
    def _imap():
        m = imaplib.IMAP4_SSL(os.environ["SOCIAL_MAIL_HOST"], 993)
        m.login(os.environ["SOCIAL_MAIL"], os.environ["SOCIAL_MAIL_PASSWORD"])
        m.select("INBOX")
        return m

    @classmethod
    def _ids(cls, m) -> set[bytes]:
        return set((m.search(None, "ALL")[1][0] or b"").split())

    def otp_email(self, soggetto: str, invia, timeout: float = 240) -> str:
        """Fotografa la inbox, esegue `invia()` (il click che fa partire l'OTP) e restituisce il codice
        (5-8 cifre) della prima email nuova col soggetto. Mai un secondo invio in automatico: OpenAPI
        smette di mandare OTP dopo ~6 richieste in 15 minuti (2026-09-25)."""
        m = self._imap()
        try:
            prima = self._ids(m)
        finally:
            m.logout()
        invia()
        fine, nuove = time.monotonic() + timeout, set()
        while time.monotonic() < fine:
            time.sleep(5)
            m = self._imap()
            try:
                nuove = self._ids(m) - prima
                for i in sorted(nuove, key=int):
                    msg = email.message_from_bytes(m.fetch(i, "(RFC822)")[1][0][1])
                    if soggetto.lower() not in str(make_header(decode_header(msg["Subject"] or ""))).lower():
                        continue
                    corpo = "".join(p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
                                    for p in msg.walk() if p.get_content_type() in ("text/plain", "text/html"))
                    trovato = re.search(r"\b(\d{5,8})\b", re.sub(r"<[^>]+>", " ", corpo))
                    if trovato:
                        return trovato.group(1)
            finally:
                m.logout()
        raise RuntimeError(f"OTP non arrivato in {timeout:.0f} s ({len(nuove)} email nuove, nessuna con '{soggetto}')")


def battute_scenario(percorso: Path) -> list[str]:
    """Testi di reel.battuta("...") nel sorgente, in ordine di comparsa: validati sul TESTO prima di
    aprire il browser. ast.walk e' un attraversamento in ampiezza (BFS), quindi NON e' l'ordine del
    sorgente appena una battuta e' annidata piu' in profondita' di una successiva (es. dentro un
    `with`); si riordina esplicitamente per (riga, colonna)."""
    albero = ast.parse(Path(percorso).read_text(encoding="utf-8"))
    nodi = [n for n in ast.walk(albero)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "battuta"
            and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)]
    nodi.sort(key=lambda n: (n.lineno, n.col_offset))
    return [n.args[0].value for n in nodi]


def esegui_scena(sc, page, reel: Reel) -> None:
    try:
        sc.scena(page, reel)
    finally:
        if reel._pulizie:
            reel._segna("fine")   # da qui in poi e' pulizia (annulla ordine, elimina listino...): fuori dal reel
        reel.pulisci()
