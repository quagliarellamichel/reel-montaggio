# Sorgenti musica di sottofondo

Tutte le tracce provengono dall'album "Calm Pills - Relaxing Ambient Music" di
Alaeddin Hallak, pubblicato su Internet Archive sotto **CC0 1.0 Universal (Public
Domain Dedication)** — uso commerciale libero, nessuna attribuzione richiesta.

Pagina item: https://archive.org/details/CalmPills
Licenza dichiarata: http://creativecommons.org/publicdomain/zero/1.0/

Pixabay (https://pixabay.com/music/) è stato tentato per primo come da brief, ma
le pagine dei brani sono dietro una challenge JS di Cloudflare: `curl`/`WebFetch`
ricevono solo l'interstitial "Just a moment...", senza URL diretto al file audio.
Da qui il fallback a una fonte CC0 con URL diretti verificabili via HTTP.

Ogni traccia è stata scaricata in streaming direttamente dall'URL di Internet
Archive (senza salvare il file originale, ~140 MB ciascuno) e ritagliata ai primi
60 secondi, scartando lo stream immagine di copertina incorporato nell'mp3
sorgente (altrimenti il file finale saliva a ~1,5 MB):

```
ffmpeg -i "<url archive.org>" -t 60 -map 0:a -c:a libmp3lame -b:a 96k music/NN-nome.mp3
```

| File | Titolo originale | Autore | URL sorgente | Licenza | Download |
|---|---|---|---|---|---|
| `01-still-habitat.mp3` | Calm Pill 1 - Still Habitat | Alaeddin Hallak | https://archive.org/download/CalmPills/Uplifting_Pills_-_Calm_Pill_1_-_Still_Habitat.mp3 | CC0 1.0 | 2026-09-25 |
| `02-heaven-sings.mp3` | Calm Pill 21 - Heaven Sings | Alaeddin Hallak | https://archive.org/download/CalmPills/Uplifting_Pills_-_Calm_Pill_21_-_Heaven_Sings.mp3 | CC0 1.0 | 2026-09-25 |
| `03-one.mp3` | Calm Pill 36 - One | Alaeddin Hallak | https://archive.org/download/CalmPills/Uplifting_Pills_-_Calm_Pill_36_-_One.mp3 | CC0 1.0 | 2026-09-25 |

Ogni traccia originale è un mix ambient di ~1 ora; qui si usano solo i primi 60
secondi di ciascuna, che bastano a coprire la durata di un reel.
