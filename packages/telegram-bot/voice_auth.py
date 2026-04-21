"""
HoFi — Voice Authentication
Autenticación biométrica por voz usando librosa.

Estrategia de identificación en dos capas:

  CAPA 1 — Identificación por nombre (cuando el audio dice "Soy X"):
    Si la transcripción contiene "Soy X" o "Me llamo X", se busca primero el
    perfil de esa persona por nombre. Si la voz coincide con ese perfil
    (umbral más bajo = 0.80), se autentica. Si el nombre no está registrado,
    se inicia el registro directamente con el nombre ya conocido.

    Esta capa resuelve el caso donde dos personas de la misma familia tienen
    pitches solapados — el nombre desambigua antes de usar biometría.

  CAPA 2 — Matching puro por voz (cuando no hay nombre en el audio):
    Embedding de 98 dims comparado por similitud coseno contra todos los
    perfiles. El mejor match gana si supera SIMILARITY_THRESHOLD (0.90).

    Features del embedding:
      - MFCC mean + std     (80 dims): timbre y calidad espectral
      - Pitch F0 stats       (5 dims): frecuencia fundamental
      - Formantes LPC F1-F3  (3 dims): longitud del tracto vocal ← KEY
        Voces masculinas (~17cm): F1≈700-800 Hz, F2≈1100-1200 Hz
        Voces femeninas  (~14cm): F1≈850-950 Hz, F2≈1300-1500 Hz
      - Spectral centroid/rolloff/bandwidth (3 dims)
      - Spectral contrast    (7 dims)

No requiere PyTorch ni CUDA — solo librosa (CPU puro).
"""

import re
import unicodedata
import numpy as np
import logging
import os

logger = logging.getLogger("VoiceAuth")

SIMILARITY_THRESHOLD       = float(os.getenv("VOICE_SIMILARITY_THRESHOLD", "0.90"))
VOICE_THRESHOLD_NAMED      = float(os.getenv("VOICE_THRESHOLD_NAMED", "0.80"))
PITCH_MEAN_IDX             = 80   # Posición del F0 mean en el embedding de 98 dims

# Peso amplificador de los formantes dentro del embedding.
# Los formantes (F1, F2, F3) son el mejor discriminador para voces familiares
# con pitch solapado. Amplificamos su contribución para que la similitud coseno
# refleje diferencias de tracto vocal.
FORMANT_WEIGHT = float(os.getenv("FORMANT_WEIGHT", "3.0"))


# ── Extracción de nombre ─────────────────────────────────────────────────────

def extraer_nombre_audio(texto: str) -> str | None:
    """
    Intenta extraer un nombre del comienzo de la transcripción.
    Cubre: "Soy X", "Me llamo X".

    Retorna el nombre en title-case o None si no hay match.
    """
    if not texto:
        return None
    texto = texto.strip()
    match = re.match(
        r"(?:soy|me llamo)\s+([A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+(?:\s+[A-ZÁÉÍÓÚÜÑa-záéíóúüñ]+)?)",
        texto,
        re.IGNORECASE,
    )
    if match:
        nombre = match.group(1).strip().title()
        logger.info("VoiceAuth | nombre extraído del audio: '%s'", nombre)
        return nombre
    return None


def _normalizar_nombre(s: str) -> str:
    """
    Minúsculas + quita diacríticos. "Mouriño" → "mourino", "Iñaki" → "inaki".
    Permite que Whisper transcriba sin ñ/tildes y el lookup siga funcionando.
    """
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    sin_marcas = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return sin_marcas.lower()


def buscar_por_nombre(nombre: str, perfiles: list[dict]) -> dict | None:
    """
    Busca un perfil cuyo member_name empiece con el primer nombre dado.
    Ignora mayúsculas/minúsculas, tildes y ñ (normalización NFD).
    """
    if not nombre or not perfiles:
        return None
    tokens = _normalizar_nombre(nombre).split()
    if not tokens:
        return None
    primer_nombre = tokens[0]
    for p in perfiles:
        p_tokens = _normalizar_nombre(p["member_name"]).split()
        if p_tokens and p_tokens[0] == primer_nombre:
            logger.info("VoiceAuth | perfil encontrado por nombre: '%s'", p["member_name"])
            return p
    return None


# ── Extracción de embedding ──────────────────────────────────────────────────

def _extraer_formantes(audio: np.ndarray, sr: int, n_formantes: int = 3) -> np.ndarray:
    """
    Estima los primeros n formantes (F1, F2, F3) usando LPC.

    Los formantes capturan la longitud del tracto vocal, que difiere entre
    personas con pitch solapado (p.ej. hombre de voz alta vs mujer de voz baja).

    Retorna un array de n_formantes Hz, o zeros si falla.
    """
    import librosa

    # Pre-énfasis para realzar armónicos altos
    audio_pe = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])

    frame_len = int(0.030 * sr)          # 30 ms
    hop_len   = int(0.010 * sr)          # 10 ms
    lpc_order = 2 + int(sr / 1000)      # 18 para sr=16000

    resultados: list[list[float]] = []

    for start in range(0, len(audio_pe) - frame_len, hop_len):
        frame = audio_pe[start : start + frame_len]
        # Descartar frames silenciosos
        if np.max(np.abs(frame)) < 1e-6:
            continue
        frame = frame * np.hamming(len(frame))

        try:
            coefs = librosa.lpc(frame, order=lpc_order)
            roots = np.roots(coefs)
            # Solo raíces con parte imaginaria positiva (mitad superior del círculo)
            roots = roots[np.imag(roots) > 0.01]
            if len(roots) == 0:
                continue
            # Ángulo → frecuencia Hz
            freqs = np.angle(roots) * sr / (2 * np.pi)
            # Filtrar rango vocal hablada: 80–4500 Hz
            freqs = np.sort(freqs[(freqs > 80) & (freqs < 4500)])
            if len(freqs) >= n_formantes:
                resultados.append(freqs[:n_formantes].tolist())
        except Exception:
            continue

    if resultados:
        medias = np.mean(resultados, axis=0)
        logger.info("VoiceAuth | formantes LPC: F1=%.0f F2=%.0f F3=%.0f Hz", *medias)
        return medias
    else:
        logger.warning("VoiceAuth | formantes LPC no disponibles (audio muy corto?)")
        return np.zeros(n_formantes)


def extraer_embedding(audio_path: str) -> np.ndarray | None:
    """
    Extrae un voice embedding de 98 dimensiones:
      [0:40]   MFCC mean
      [40:80]  MFCC std
      [80:85]  Pitch F0 stats (mean, std, p10, p90, voiced_frac)
      [85:88]  Formantes F1, F2, F3 (escalados × FORMANT_WEIGHT)
      [88:91]  Spectral centroid, rolloff, bandwidth
      [91:98]  Spectral contrast (7 bands)
    """
    try:
        import librosa

        logger.info("VoiceAuth | cargando audio %s", audio_path)
        audio, sr = librosa.load(audio_path, sr=16000, mono=True)
        duracion  = len(audio) / sr
        logger.info("VoiceAuth | %.1f segundos de audio", duracion)

        # ── MFCC: 40 coefs × (mean + std) = 80 dims ─────────────────────────
        mfccs     = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=40)
        mfcc_mean = np.mean(mfccs, axis=1)
        mfcc_std  = np.std(mfccs, axis=1)

        # ── Pitch / F0 ────────────────────────────────────────────────────────
        # YIN: ~10x mas rapido que PYIN en CPU. Sin modelo HMM probabilistico.
        # voiced_flag: estimado como f0 > fmin*1.5 (~97 Hz), suficiente para
        # discriminar voz hablada de silencio/ruido en rangos 110-260 Hz.
        fmin_hz = librosa.note_to_hz("C2")   # ~65 Hz
        fmax_hz = librosa.note_to_hz("C7")   # ~2093 Hz
        f0 = librosa.yin(
            audio,
            fmin=fmin_hz,
            fmax=fmax_hz,
            sr=sr,
        )
        voiced_flag = f0 > (fmin_hz * 1.5)   # ~97 Hz threshold
        f0_voiced   = f0[voiced_flag]
        if len(f0_voiced) > 0:
            pitch_feats = np.array([
                np.mean(f0_voiced),                   # [80] F0 mean
                np.std(f0_voiced),                    # [81] F0 std
                np.percentile(f0_voiced, 10),         # [82] F0 p10
                np.percentile(f0_voiced, 90),         # [83] F0 p90
                np.mean(voiced_flag.astype(float)),   # [84] voiced fraction
            ])
        else:
            pitch_feats = np.zeros(5)

        logger.info(
            "VoiceAuth | pitch: %.1f Hz (std=%.1f, %.0f%% vocalizado)",
            pitch_feats[0], pitch_feats[1], pitch_feats[4] * 100,
        )

        # ── Formantes LPC: F1, F2, F3 × FORMANT_WEIGHT ───────────────────────
        # Tracto vocal masculino (~17cm) → F1≈700-800 Hz, F2≈1100-1200 Hz
        # Tracto vocal femenino  (~14cm) → F1≈850-950 Hz, F2≈1300-1500 Hz
        # El peso amplificador hace que esta diferencia impacte en la similitud coseno.
        formantes      = _extraer_formantes(audio, sr, n_formantes=3)
        formantes_pesados = formantes * FORMANT_WEIGHT

        # ── Spectral features ─────────────────────────────────────────────────
        spec_centroid = float(np.mean(librosa.feature.spectral_centroid(y=audio, sr=sr)))
        spec_rolloff  = float(np.mean(librosa.feature.spectral_rolloff(y=audio, sr=sr)))
        spec_bandw    = float(np.mean(librosa.feature.spectral_bandwidth(y=audio, sr=sr)))
        spec_contrast = np.mean(librosa.feature.spectral_contrast(y=audio, sr=sr), axis=1)

        # ── Embedding final: 80 + 5 + 3 + 3 + 7 = 98 dims ───────────────────
        embedding = np.concatenate([
            mfcc_mean,
            mfcc_std,
            pitch_feats,
            formantes_pesados,
            [spec_centroid, spec_rolloff, spec_bandw],
            spec_contrast,
        ])

        logger.info(
            "VoiceAuth | embedding OK — %d dims, norm=%.1f",
            len(embedding), float(np.linalg.norm(embedding)),
        )
        return embedding

    except Exception as e:
        logger.error("VoiceAuth | error: %s — %s", type(e).__name__, str(e))
        return None


def promediar_embeddings(embeddings: list) -> np.ndarray:
    """
    Calcula el centroide (promedio) de una lista de embeddings.
    Dos muestras promediadas reducen el ruido del enrollment de una sola muestra.
    """
    stack    = np.array([np.array(e, dtype=np.float32) for e in embeddings])
    centroid = np.mean(stack, axis=0)
    logger.info(
        "VoiceAuth | centroide de %d muestras — F0=%.1f Hz, F1≈%.0f Hz",
        len(embeddings),
        centroid[PITCH_MEAN_IDX] if len(centroid) > PITCH_MEAN_IDX else 0,
        centroid[85] / FORMANT_WEIGHT if len(centroid) > 85 else 0,
    )
    return centroid


# ── Comparación ──────────────────────────────────────────────────────────────

def similitud_coseno(emb1: list | np.ndarray, emb2: list | np.ndarray) -> float:
    """Similitud coseno entre dos embeddings. Rango: -1 a 1."""
    a = np.array(emb1, dtype=np.float32)
    b = np.array(emb2, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def autenticar(embedding_nuevo: np.ndarray, perfiles: list[dict]) -> dict | None:
    """
    Comparación pura por voz — sin nombre en el audio.
    Retorna el perfil con mayor similitud coseno si supera SIMILARITY_THRESHOLD.
    """
    if not perfiles:
        return None

    mejor_perfil    = None
    mejor_similitud = 0.0

    for perfil in perfiles:
        sim = similitud_coseno(embedding_nuevo, perfil["voice_embedding"])
        logger.info("VoiceAuth | similitud coseno con %s: %.4f", perfil["member_name"], sim)
        if sim > mejor_similitud:
            mejor_similitud = sim
            mejor_perfil    = perfil

    if mejor_perfil and mejor_similitud >= SIMILARITY_THRESHOLD:
        logger.info("VoiceAuth | autenticado: %s (%.4f)", mejor_perfil["member_name"], mejor_similitud)
        return {**mejor_perfil, "similitud": mejor_similitud}

    logger.info("VoiceAuth | no autenticado — mejor=%.4f (umbral=%.2f)", mejor_similitud, SIMILARITY_THRESHOLD)
    return None


def autenticar_por_nombre(nombre: str, embedding_nuevo: np.ndarray, perfiles: list[dict]) -> dict | None:
    """
    Autenticación dirigida: busca el perfil del nombre dado y verifica la voz
    con un umbral más bajo (VOICE_THRESHOLD_NAMED=0.80) porque el nombre
    ya acota el espacio de búsqueda.

    Retorna el perfil si la voz coincide, o None si:
      - El nombre no está registrado (→ iniciar registro)
      - La voz no coincide con ese perfil
    """
    perfil = buscar_por_nombre(nombre, perfiles)
    if perfil is None:
        logger.info("VoiceAuth | '%s' no está registrado → iniciar registro", nombre)
        return None

    sim = similitud_coseno(embedding_nuevo, perfil["voice_embedding"])
    logger.info(
        "VoiceAuth | verificación por nombre '%s': sim=%.4f (umbral_named=%.2f)",
        nombre, sim, VOICE_THRESHOLD_NAMED,
    )

    if sim >= VOICE_THRESHOLD_NAMED:
        logger.info("VoiceAuth | autenticado por nombre+voz: %s (%.4f)", perfil["member_name"], sim)
        return {**perfil, "similitud": sim}

    # Voz demasiado distinta al perfil con ese nombre — posiblemente homofonía
    logger.info(
        "VoiceAuth | voz no coincide con perfil '%s' (%.4f < %.2f)",
        perfil["member_name"], sim, VOICE_THRESHOLD_NAMED,
    )
    return None
