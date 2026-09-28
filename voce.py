"""Voce dei reel: Gemini TTS (voce Kore) sul testo intero + sottotitoli dai silenzi."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import time
import wave
from pathlib import Path

import httpx

# Stile come tag tra parentesi quadre: gemini-3.8-flash-tts legge ad alta voce QUALSIASI prefisso
# testuale ("Leggi con tono...:" in italiano o inglese) e rifiuta systemInstruction; i tag no
# (provato 2026-09-25 con trascrizione di verifica). Il controllo resta in sintetizza_verificata.
STILE = "[relaxed, warm, conversational, no advertising emphasis]"
API = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def prompt_tts(testo: str) -> str:
    return f"{STILE} {' '.join(testo.split())}"


def _parole(s: str) -> list[str]:
    return re.findall(r"[a-zàèéìòù']+", s.lower())


def inizia_con(trascritto: str, testo: str, n: int = 4) -> bool:
    """True se la trascrizione inizia con le prime n parole del testo (punteggiatura/maiuscole ignorate)."""
    atteso = _parole(testo)[:n]
    return _parole(trascritto)[:n] == atteso


def trascrivi_inizio(wav: Path, api_key: str, modello: str = "gemini-flash-latest") -> str:
    body = {"contents": [{"parts": [
        {"text": "Trascrivi parola per parola le prime dieci parole pronunciate in questo audio. "
                 "Rispondi solo con la trascrizione."},
        {"inlineData": {"mimeType": "audio/wav", "data": base64.b64encode(wav.read_bytes()).decode("ascii")}},
    ]}]}
    r = httpx.post(API.format(m=modello), json=body, headers={"x-goog-api-key": api_key}, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini trascrizione HTTP {r.status_code}: {r.text[:300]}")
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def sintetizza(testo: str, api_key: str, voce: str = "Kore", modello: str = "gemini-3.8-flash-tts") -> bytes:
    # Testo intero in una chiamata: spezzarlo in frasi peggiora l'intonazione (provato 2026-09-25).
    body = {
        "contents": [{"parts": [{"text": prompt_tts(testo)}]}],
        "generationConfig": {"responseModalities": ["AUDIO"],
                             "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voce}}}},
    }
    r = httpx.post(API.format(m=modello), json=body, headers={"x-goog-api-key": api_key}, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini TTS HTTP {r.status_code}: {r.text[:300]}")
    return base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])


def sintetizza_verificata(testo: str, api_key: str, wav: Path, tentativi: int = 3) -> None:
    """Sintetizza in wav e controlla che l'audio inizi col testo (non con l'istruzione di stile)."""
    ultimo = ""
    for i in range(tentativi):
        if i:
            time.sleep(25)  # tier gratuito: 3 richieste/minuto per modello
        salva_wav(sintetizza(testo, api_key), wav)
        ultimo = trascrivi_inizio(wav, api_key)
        if inizia_con(ultimo, testo):
            return
    raise RuntimeError(f"La voce non inizia col testo dopo {tentativi} tentativi. Inizio sentito: {ultimo[:120]!r}")


def salva_wav(pcm: bytes, percorso: Path) -> None:
    with wave.open(str(percorso), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(pcm)


def frasi(testo: str) -> list[str]:
    return [f.strip() for f in re.findall(r"[^.?!]+(?:[.?!]+|$)", testo) if f.strip()]


def parse_silencedetect(stderr: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", stderr)]
    return list(zip(starts, ends))


def cue(frasi: list[str], silenzi: list[tuple[float, float]], durata: float,
        tolleranza: float = 1.5) -> list[tuple[float, float, str]]:
    """Confine tra frasi = stima proporzionale ai caratteri, agganciata alla pausa piu' vicina
    entro `tolleranza` secondi. Le pause piu' lunghe non bastano: la voce ne fa anche a meta' frase
    (reel 2026-09-25: "Ecco." restava a schermo 7 s)."""
    tot = sum(len(f) for f in frasi) or 1
    medi = [round((a + b) / 2, 3) for a, b in silenzi]
    acc, confini, ultimo = 0, [], 0.0
    for f in frasi[:-1]:
        acc += len(f)
        stima = durata * acc / tot
        vicini = [m for m in medi if m > ultimo and abs(m - stima) <= tolleranza]
        ultimo = min(vicini, key=lambda m: abs(m - stima)) if vicini else round(max(stima, ultimo), 3)
        confini.append(ultimo)
    bordi = [0.0] + confini + [durata]
    return [(bordi[i], bordi[i + 1], f) for i, f in enumerate(frasi)]


def _ts(s: float) -> str:
    ms = round(s * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def srt(cues: list[tuple[float, float, str]]) -> str:
    return "\n".join(f"{i}\n{_ts(a)} --> {_ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1))


def silenzi_wav(percorso: Path) -> tuple[list[tuple[float, float]], float]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(percorso), "-af",
                        "silencedetect=noise=-40dB:d=0.25", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    with wave.open(str(percorso)) as w:
        durata = w.getnframes() / w.getframerate()
    return parse_silencedetect(p.stderr), durata


def spezza(cues: list[tuple[float, float, str]], max_parole: int = 5) -> list[tuple[float, float, str]]:
    """Frasi -> pezzi di al massimo `max_parole` parole (stile reel: 1-2 righe), con il tempo della
    frase diviso in proporzione ai caratteri. Pezzi contigui: mai due sottotitoli insieme."""
    out = []
    for a, b, testo in cues:
        pezzi = []
        # prima si spezza alle pause naturali (virgole, due punti, punto e virgola), poi per lunghezza
        for clausola in re.findall(r"[^,;:]+[,;:]?", testo):
            parole = clausola.split()
            if not parole:
                continue
            n = max(1, -(-len(parole) // max_parole))      # numero pezzi, arrotondato in su
            passo = -(-len(parole) // n)                    # parole per pezzo, bilanciate
            pezzi += [" ".join(parole[i:i + passo]) for i in range(0, len(parole), passo)]
        tot = sum(len(p) for p in pezzi) or 1
        t = a
        for i, p in enumerate(pezzi):
            fine = b if i == len(pezzi) - 1 else round(t + (b - a) * len(p) / tot, 3)
            out.append((t, fine, p))
            t = fine
    return out


def _ts_ass(s: float) -> str:
    cs = round(s * 100)
    return f"{cs // 360000}:{cs // 6000 % 60:02}:{cs // 100 % 60:02}.{cs % 100:02}"


def _colore_ass(colore: str) -> str:
    """#rrggbb -> &H00BBGGRR (ASS vuole blu-verde-rosso, alfa 00 = opaco)."""
    return f"&H00{colore[5:7]}{colore[3:5]}{colore[1:3]}".upper()


def ass(cues: list[tuple[float, float, str]], contorno: str = "#2a3d31", orizzontale: bool = False) -> str:
    """Sottotitoli ASS a coordinate reali 1080x1920 (niente scala da 288px come per l'srt):
    bianco in grassetto con contorno del colore della palette morbido, niente box, nella fascia sotto la finestra.
    `orizzontale`: spot 16:9, 1920x1080, nella fascia sotto la finestra della cornice desktop."""
    # orizzontale: centrati sotto la finestra (FINESTRA_ORIZZONTALE x 600..1850, fondo a 870)
    rx, ry, corpo, sx, dx, basso = (1920, 1080, 58, 600, 70, 110) if orizzontale else (1080, 1920, 70, 80, 80, 140)
    testa = (
        f"[Script Info]\nScriptType: v4.00+\nPlayResX: {rx}\nPlayResY: {ry}\nWrapStyle: 0\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
        "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding\n"
        # Nome famiglia (nameID 1) dell'istanza statica font-sub.ttf: con "Plus Jakarta Sans" libass
        # prendeva font.ttf (variabile) al peso normale — verificato 2026-09-26 confrontando i frame.
        f"Style: Reel,Plus Jakarta Sans ExtraBold,{corpo},&H00FFFFFF,&H00FFFFFF,{_colore_ass(contorno)},&H96000000,-1,0,0,0,100,100,0,0,"
        f"1,6,2,2,{sx},{dx},{basso},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    righe = [f"Dialogue: 0,{_ts_ass(a)},{_ts_ass(b)},Reel,,0,0,0,,{t}" for a, b, t in cues]
    return testa + "\n".join(righe) + "\n"


def pezzi_testo(testo: str) -> list[str]:
    """Pezzi di sottotitolo del testo, senza audio: servono a validare le battute prima di girare."""
    return [p for _, _, p in spezza(cue(frasi(testo), [], 1.0))]


def pezzi_audio(wav: Path, testo: str) -> tuple[list[tuple[float, float, str]], float]:
    """Pezzi di sottotitolo con i tempi della voce registrata, piu' la durata della voce."""
    silenzi, durata = silenzi_wav(wav)
    return spezza(cue(frasi(testo), silenzi, durata)), durata


def indice_battuta(battuta: str, pezzi: list[tuple[float, float, str]]) -> int:
    """Indice del pezzo in cui inizia la battuta (puo' proseguire nei pezzi successivi). Maiuscole
    e punteggiatura non contano. Stessa regola di ricerca di trova_battuta, ma restituisce
    l'indice invece del secondo: serve a validare l'ordine delle battute prima di registrare."""
    cercate = _parole(battuta)
    if cercate:
        for i, (_, _, _) in enumerate(pezzi):
            seguito = _parole(" ".join(p for _, _, p in pezzi[i:]))
            if seguito[:len(cercate)] == cercate:
                return i
    validi = " | ".join(p for _, _, p in pezzi)
    raise ValueError(f"Battuta non trovata nel testo: {battuta!r}. Deve iniziare come uno di questi pezzi: {validi}")


def trova_battuta(battuta: str, pezzi: list[tuple[float, float, str]]) -> float:
    """Secondo della voce in cui inizia la battuta: deve coincidere con l'inizio di un pezzo di
    sottotitolo (puo' proseguire nei pezzi successivi). Maiuscole e punteggiatura non contano."""
    return pezzi[indice_battuta(battuta, pezzi)][0]


def firma_voce(testo: str) -> str:
    """La voce si rigenera solo se cambia cio' che si sente: testo, stile, voce, modello."""
    return hashlib.sha256(f"{STILE}|Kore|gemini-3.8-flash-tts|{' '.join(testo.split())}".encode()).hexdigest()[:16]


def voce_attuale(cartella: Path, testo: str) -> bool:
    j = cartella / "voce.json"
    if not (cartella / "voce.wav").exists() or not j.exists():
        return False
    return json.loads(j.read_text(encoding="utf-8")).get("firma") == firma_voce(testo)


def segna_voce(cartella: Path, testo: str) -> None:
    (cartella / "voce.json").write_text(json.dumps({"firma": firma_voce(testo)}), encoding="utf-8")
