# reel-montaggio

Produce reel verticali 9:16 (Instagram / YouTube Shorts / TikTok) e spot 16:9 **registrando una web app
vera** con Playwright, con voce sintetica, sottotitoli, musica e una "telecamera" che segue l'azione.

Scrivi uno scenario Python (cosa cliccare, cosa indicare, cosa dice la voce), lanci un comando, esce
un `.mp4` pronto da pubblicare. I ritocchi (tagli, velocità, zoom, hook) si fanno sulla timeline,
senza rigirare.

## Come funziona

```
scenario.py ──► Playwright registra il browser 1920x1080 (rec.webm)
                 │  ogni evento (fuoco, taglio, battuta) cambia colore a un marcatore
                 │  di 8 px nell'angolo: il montaggio legge dal video il tempo esatto
                 ▼
             timeline.json  ◄── reel.py (taglia, velocita, fuoco, zoom, hook, palette, annulla)
                 │
TESTO ──► Gemini TTS ──► voce.wav ──► silencedetect ──► sottotitoli .ass (max 5 parole)
                 │
                 ▼
             ffmpeg: telecamera 9:16 che fa pan/zoom tra i fuochi, tempo del video
             stirato per agganciare ogni battuta alla sua frase, cornice PNG (Playwright),
             hook, sottotitoli, voce + musica bassa
                 ▼
             out/<slug>.mp4  +  controllo.txt / foglio.png (verifica automatica)
```

| File | Ruolo |
|---|---|
| `capture.py` | CLI principale: `login`, `registra`, `voce` |
| `reel.py` | mini editor della timeline, a comandi |
| `kit.py` | API usata dagli scenari (`reel.punta`, `fuoco`, `taglio`, `battuta`, `card`, `dopo`, `otp_email`) |
| `timeline.py` | modello della timeline: tagli, velocità, fuochi, mappa tempo girato ↔ tempo reel |
| `voce.py` | TTS Gemini con verifica della trascrizione, frasi, silenzi, sottotitoli SRT/ASS |
| `montaggio.py` | costruzione del comando ffmpeg (telecamera, cornice, hook, audio) |
| `render.py` | render completo da timeline: cornice, sottotitoli, ffmpeg, controllo |
| `controllo.py` | avvisi automatici (inizio/fine vuoti, velocità estreme, battute) + foglio fotogrammi |
| `palette.py` | 5 palette colore (`assets/palette.json`), rotazione sulla meno usata |
| `registro.py` | parser del registro `reels.md` (facoltativo, usato per la rotazione palette) |
| `scenari/` | uno scenario per reel; `_esempio.py` è il contratto |

## Requisiti

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/) e ffprobe nel `PATH` (con libass per i sottotitoli)
- Una API key [Gemini](https://aistudio.google.com/apikey) (voce TTS + trascrizione di verifica)

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env      # poi compila GEMINI_API_KEY e REEL_BASE_URL
```

## Uso

### 1. Login (una volta, finché la sessione dura)

```bash
python capture.py login
```

Apre un Chromium visibile su `REEL_BASE_URL` + `REEL_LOGIN_PATH`: accedi (meglio con un account demo,
con dati finti), poi premi Invio nel terminale. La sessione finisce in `.auth.json` (gitignorato).

### 2. Scrivi lo scenario

Copia `scenari/_esempio.py` in `scenari/<slug>.py` (slug: `a-z`, `0-9`, `-`):

```python
TITOLO = "Preventivo di gruppo"
HOOK = "Il cliente vuole il preventivo\ndel gruppo. Adesso."   # testo in alto, \n = a capo
TESTO = "Sai quando il cliente chiede il prezzo del gruppo? Metti le camere e il totale è pronto. Trenta giorni di prova, gratis."
CAPTION = "Caption del post.\n\n#hashtag"
SENSIBILI = [".nome-cliente"]          # selettori CSS sfocati nel girato
PALETTE = "blu-mare"                   # facoltativo, altrimenti rotazione automatica
ZOOM_TELECAMERA = 1.25                 # facoltativo, zoom di default
CHIP = "NOVITÀ"                        # facoltativo, etichetta della cornice

def scena(page, reel):
    page.goto(page.url.rstrip("/") + "/preventivi")
    reel.punta("#nuovo", zoom=1.8)                 # anello + cursore sul bottone, la camera lo segue
    reel.battuta("Metti le camere")                # da qui il video va a tempo con questa frase
    page.click("#nuovo")
    with reel.taglio():                            # attesa tolta dal reel
        page.wait_for_selector(".risultato")
    reel.punta(".risultato", zoom=1.35, lento=1.2) # pan lento su una riga intera
    reel.card("RIEPILOGO", [("Camere", "4"), ("Totale", "2.480 €")], nota="Calcolato in 2 secondi")
    reel.dopo(lambda: page.click("#elimina"))      # pulizia, eseguita anche se la scena fallisce
```

Regole pratiche per la camera:

- `punta` indica cosa si sta guardando (anello + cursore) e muove la camera; `fuoco` muove solo la camera.
- Pan standard 0,9 s; `lento=N` per una deriva più lunga.
- `zoom` stretto (1,8-1,9) su celle e bottoni, largo (1,35) su righe intere; sotto 24 px la camera non si muove.
- L'anello è a coordinate fisse: `reel.spunta()` prima di scorrere la pagina (lo scroll dentro un `taglio`).
- Ogni `battuta("...")` deve essere l'inizio di un pezzo di sottotitolo del `TESTO`, in ordine, e non il
  primo: viene validato **prima** di aprire il browser.

### 3. Registra

```bash
python capture.py registra <slug>                    # gira, voce, render, controllo
python capture.py registra <slug> --voce-nuova       # rigenera la voce anche se il TESTO non è cambiato
python capture.py registra <slug> --palette viola-sera
```

Output:

- `out/<slug>.mp4` — il reel
- `work/<slug>/timeline.json` — la timeline modificabile
- `work/<slug>/controllo.txt` — avvisi automatici, **da leggere**
- `work/<slug>/foglio.png` — foglio fotogrammi per un controllo a colpo d'occhio

Se la scena fallisce, il girato parziale resta in `work/<slug>/rec-fallito.webm` e la timeline
precedente non viene toccata.

### 4. Ritocca senza rigirare

I tempi sono quelli del **reel** (quelli che vedi nel video e nel foglio fotogrammi).

```bash
python reel.py <slug> mostra                 # tratti, tagli, fuochi, battute con i tempi
python reel.py <slug> anteprima 3.5 8 12     # fotogrammi a quei tempi
python reel.py <slug> taglia 4.2 6.0         # toglie un pezzo
python reel.py <slug> ripristina 0           # rimette il taglio n. 0
python reel.py <slug> velocita 10 14 1.5     # accelera un tratto
python reel.py <slug> fuoco 7.0 960 540      # aggiunge un fuoco (coordinate del girato 1920x1080)
python reel.py <slug> sposta-fuoco 2 40 -20  # sposta il fuoco n. 2
python reel.py <slug> togli-fuoco 2
python reel.py <slug> zoom 1.4               # zoom di default della telecamera
python reel.py <slug> hook "Nuovo hook\nsu due righe"
python reel.py <slug> palette terracotta     # la card finale resta del colore del girato
python reel.py <slug> render                 # rimonta out/<slug>.mp4
python reel.py <slug> render --formato orizzontale   # spot 16:9 -> out/<slug>-16x9.mp4
python reel.py <slug> annulla                # torna alla versione precedente della timeline
```

Ogni modifica salva la versione precedente in `timeline.N.json`.

### 5. Nuovo testo sullo stesso girato

Cambia `TESTO` nello scenario, poi:

```bash
python capture.py voce <slug>
```

Rifà voce, sottotitoli e render; le battute devono ancora combaciare col nuovo testo.

## Personalizzazione

- **Cornice** (chip, finestra browser, firma in basso): `assets/cornice.html`.
- **Palette**: `assets/palette.json` (sfondo, accento, colori card; i contrasti vengono validati).
  Se esiste un `reels.md` (formato in `registro.py`) la rotazione sceglie la palette meno usata di recente.
- **Font**: Plus Jakarta Sans (SIL OFL 1.1, vedi `assets/NOTE.md`).
- **Musica**: 3 tracce CC0 in `music/` (fonti in `music/SOURCES.md`), scelte in modo deterministico dallo slug.
- **Voce**: `voce.sintetizza(..., voce="Kore")`, qualsiasi voce Gemini TTS.

## Test

```bash
python -m pytest -q
```

I test non richiedono rete né ffmpeg: coprono timeline, montaggio (costruzione dei filtri),
sottotitoli, palette, kit e CLI.

## Privacy

`.env`, `.auth*.json`, `work/` e `out/` sono gitignorati: la sessione del browser e i girati non
finiscono nel repo. I selettori in `SENSIBILI` (più email, telefono e nome utente di default) vengono
sfocati via CSS **durante** la registrazione, quindi non esistono in chiaro nemmeno nel girato.

## Licenza

Codice: [MIT](LICENSE). Font Plus Jakarta Sans: SIL OFL 1.1 (`assets/OFL.txt`). Musica: CC0 (`music/SOURCES.md`).
