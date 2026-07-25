import logging

logger = logging.getLogger("legendas")

# Mapeamento amigável de idiomas suportados
SUPPORTED_LANGUAGES = {
    "pt-BR": "Português (Brasil)",
    "en": "Inglês (English)",
    "es": "Espanhol (Español)",
    "fr": "Francês (Français)",
    "de": "Alemão (Deutsch)",
    "it": "Italiano (Italiano)",
    "ja": "Japonês (日本語)",
    "zh": "Chinês (中文)",
    "ru": "Russo (Русский)",
    "ko": "Coreano (한국어)"
}

def translate_text(text: str, target_lang: str = "pt-BR", source_lang: str = "auto") -> str:
    """
    Traduz um texto individual para o idioma alvo desejado (Padrão: pt-BR).
    Utiliza deep-translator (Google Translate Engine) com fallbacks locais seguros.
    """
    if not text or not text.strip():
        return ""

    # Normalizar códigos de idioma
    target_code = target_lang.lower().strip()
    if target_code in ["pt-br", "pt_br", "portuguese"]:
        target_code = "pt"
    elif target_code in ["en-us", "english"]:
        target_code = "en"
    elif target_code in ["es-es", "spanish"]:
        target_code = "es"

    source_code = source_lang.lower().strip() if source_lang else "auto"
    if source_code == target_code:
        return text.strip()

    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source=source_code, target=target_code)
        translated = translator.translate(text)
        return translated.strip() if translated else text
    except Exception as e:
        logger.warning(f"Aviso na tradução via deep-translator ({e}). Tentando fallback local...")
        try:
            import argostranslate.translate
            translated = argostranslate.translate.translate(text, source_code, target_code)
            return translated.strip() if translated else text
        except Exception:
            logger.error(f"Erro completo ao traduzir trecho: '{text[:30]}...' -> Mantendo texto original.")
            return text

def translate_segments(
    segments: list[dict], 
    target_lang: str = "pt-BR", 
    source_lang: str = "auto"
) -> list[dict]:
    """
    Traduz uma lista de segmentos transcritos pelo Whisper para o idioma alvo (Padrão: pt-BR).
    Atualiza 'translated_text' em cada segmento.
    """
    if not segments:
        return []

    logger.info(f"Sal0 Legendas - Traduzindo {len(segments)} segmentos (Origem: {source_lang} -> Destino: {target_lang})...")
    
    # Se o idioma de origem já for o idioma alvo, mantemos o texto traduzido igual ao original
    t_code = target_lang.lower().strip()
    s_code = source_lang.lower().strip() if source_lang else "auto"
    
    if (t_code in ["pt", "pt-br", "pt_br"] and s_code in ["pt", "por", "portuguese"]) or (t_code == s_code and s_code != "auto"):
        logger.info("Idioma original é idêntico ao idioma alvo. Pulando tradução.")
        for seg in segments:
            seg["translated_text"] = seg.get("original_text", seg.get("text", ""))
            seg["text"] = seg["translated_text"]
        return segments

    translated_count = 0
    for seg in segments:
        orig = seg.get("original_text") or seg.get("text", "")
        if orig:
            translated = translate_text(orig, target_lang=target_lang, source_lang=source_lang)
            seg["translated_text"] = translated
            # 'text' conterá o texto que será renderizado/exibido (traduzido por padrão)
            seg["text"] = translated
            translated_count += 1

    logger.info(f"Tradução de {translated_count} segmentos concluída com sucesso.")
    return segments
