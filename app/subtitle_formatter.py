import os
import math
import logging

logger = logging.getLogger("legendas")

def format_timestamp_srt(seconds: float) -> str:
    """Converte segundos para o formato SRT: HH:MM:SS,mmm"""
    if is_nan_or_negative(seconds):
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - math.floor(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_timestamp_vtt(seconds: float) -> str:
    """Converte segundos para o formato WebVTT: HH:MM:SS.mmm"""
    if is_nan_or_negative(seconds):
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - math.floor(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

def format_timestamp_ass(seconds: float) -> str:
    """Converte segundos para o formato ASS: H:MM:SS.cc"""
    if is_nan_or_negative(seconds):
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - math.floor(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    return f"{hours:01d}:{minutes:02d}:{secs:02d}.{centis:02d}"

def is_nan_or_negative(val):
    try:
        return math.isnan(val) or val < 0
    except Exception:
        return True

def hex_to_ass_color(hex_color: str, alpha_hex: str = "00") -> str:
    """Converte de #RRGGBB para formato ASS &HAA%B%G%R"""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"&H{alpha_hex}{b}{g}{r}"
    return f"&H{alpha_hex}FFFFFF"

def generate_srt(segments: list[dict], output_path: str, use_translated: bool = True) -> str:
    """Gera um arquivo de legenda no formato padrão SRT (.srt)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    lines = []
    for idx, seg in enumerate(segments, 1):
        start_str = format_timestamp_srt(seg.get("start", 0))
        end_str = format_timestamp_srt(seg.get("end", 0))
        txt = seg.get("translated_text" if use_translated else "original_text", seg.get("text", "")).strip()
        
        lines.append(f"{idx}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(txt)
        lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def generate_vtt(segments: list[dict], output_path: str, use_translated: bool = True) -> str:
    """Gera um arquivo de legenda no formato WebVTT (.vtt)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    lines = ["WEBVTT", ""]
    for idx, seg in enumerate(segments, 1):
        start_str = format_timestamp_vtt(seg.get("start", 0))
        end_str = format_timestamp_vtt(seg.get("end", 0))
        txt = seg.get("translated_text" if use_translated else "original_text", seg.get("text", "")).strip()
        
        lines.append(f"{idx}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(txt)
        lines.append("")

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def generate_txt(segments: list[dict], output_path: str, use_translated: bool = True) -> str:
    """Gera uma transcrição simples em texto puro (.txt)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    lines = []
    for seg in segments:
        txt = seg.get("translated_text" if use_translated else "original_text", seg.get("text", "")).strip()
        if txt:
            lines.append(txt)

    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path

def generate_ass(
    segments: list[dict],
    output_path: str,
    font_size: int = 24,
    text_color_hex: str = "#FFFFFF",
    text_position: str = "bottom",
    use_translated: bool = True,
    show_box_background: bool = True
) -> str:
    """
    Gera um arquivo de legenda estilizado no formato Advanced SubStation Alpha (.ass).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Mapeamento de alinhamento ASS (Numpad)
    # 2 = Bottom Center, 5 = Middle Center, 8 = Top Center
    alignment = 2
    if text_position == "middle":
        alignment = 5
    elif text_position == "top":
        alignment = 8

    primary_color = hex_to_ass_color(text_color_hex, "00")  # Opaco
    outline_color = hex_to_ass_color("#000000", "00")
    back_color = hex_to_ass_color("#000000", "60") if show_box_background else hex_to_ass_color("#000000", "00")

    border_style = 3 if show_box_background else 1  # 3 = Box opaco/semi-transparente, 1 = Borda/Contorno

    ass_header = f"""[Script Info]
Title: Sal0 Legendas
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},{primary_color},&H000000FF,{outline_color},{back_color},1,0,0,0,100,100,0,0,{border_style},2,1,{alignment},20,20,30,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for seg in segments:
        start_str = format_timestamp_ass(seg.get("start", 0))
        end_str = format_timestamp_ass(seg.get("end", 0))
        txt = seg.get("translated_text" if use_translated else "original_text", seg.get("text", "")).strip()
        
        # Quebrar linhas longas
        txt_ass = txt.replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{txt_ass}")

    content = ass_header + "\n".join(events) + "\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
