#!/usr/bin/env python3
"""Gera SVG de background para Nextcloud usando a mesma lógica do RPA4All.com."""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error, request
from zoneinfo import ZoneInfo
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Variant:
    variant_id: str
    focus: str


VARIANTS = [
    Variant("control-mesh", "an asymmetrical control mesh with monitoring arcs and clean routing lines"),
    Variant("precision-field", "a precision field of emerald and cyan trajectories with layered telemetry halos"),
    Variant("signal-archipelago", "signal islands connected by data bridges, packet trails and subtle observability rings"),
    Variant("orchestration-fold", "folded orchestration planes with modular panels and soft pulse waves"),
    Variant("resilience-constellation", "a resilience constellation with anchored nodes, recovery pulses and a faint technical grid"),
    Variant("data-current", "flowing data currents sweeping diagonally over a dark command surface with sparse nodes"),
]


def get_season_brazil(month_index: int) -> str:
    if month_index == 12 or month_index <= 2:
        return "verao"
    if 3 <= month_index <= 5:
        return "outono"
    if 6 <= month_index <= 8:
        return "inverno"
    return "primavera"


def detect_brazil_holiday(month: int, day: int) -> str:
    fixed = {
        "01-01": "Confraternizacao Universal",
        "04-21": "Tiradentes",
        "05-01": "Dia do Trabalho",
        "09-07": "Independencia do Brasil",
        "10-12": "Nossa Senhora Aparecida / Dia das Criancas",
        "11-02": "Finados",
        "11-15": "Proclamacao da Republica",
        "12-25": "Natal",
    }
    return fixed.get(f"{month:02d}-{day:02d}", "")


def resolve_context() -> dict[str, str]:
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    hour = now.hour
    if hour < 5:
        part_of_day = "madrugada"
    elif hour < 12:
        part_of_day = "manha"
    elif hour < 18:
        part_of_day = "tarde"
    else:
        part_of_day = "noite"

    season = get_season_brazil(now.month)
    holiday = detect_brazil_holiday(now.month, now.day)
    weather_label = (
        "ceu limpo com umidade leve"
        if season == "verao"
        else "ceu frio e seco"
        if season == "inverno"
        else "ceu aberto ameno"
    )
    temperature_label = (
        "clima quente" if season == "verao" else "clima fresco" if season == "inverno" else "clima ameno"
    )
    return {
        "part_of_day": part_of_day,
        "season": season,
        "holiday": holiday,
        "weather_label": weather_label,
        "temperature_label": temperature_label,
    }


def build_prompt(variant: Variant, seed: int, ctx: dict[str, str]) -> str:
    holiday_line = (
        f"Today is {ctx['holiday']} in Brazil; weave a respectful celebratory glow using flag colors without text."
        if ctx["holiday"]
        else "No holiday today; keep the tone executive with only subtle festivity."
    )
    return " ".join(
        [
            "Generate ONLY a valid SVG image.",
            "Do not include markdown, prose, code fences, comments, explanations, base64 PNGs or embedded raster images.",
            "Return raw SVG starting with <svg and ending with </svg>.",
            'Width="1600" height="900" viewBox="0 0 1600 900".',
            "Create a simple abstract website background for the brand RPA4ALL.",
            "Visual direction: dark command center, premium automation platform and data movement.",
            "Use deep navy as the base and emerald #22c55e, cyan #38bdf8, teal #14b8a6 and yellow #facc15 as highlights.",
            "No text, no letters, no numbers, no logos, no people.",
            "Use only gradients, paths, circles, soft glows, technical grids, telemetry arcs and flowing lines.",
            "Avoid centered logo-like symbols and avoid repetitive mirrored petals.",
            "Favor wide composition with multiple layers spread across the canvas.",
            "Keep the SVG lightweight and elegant, with negative space for UI content.",
            f"Context: {ctx['part_of_day']} in Brazil, season {ctx['season']}, {ctx['weather_label']}, {ctx['temperature_label']}.",
            holiday_line,
            "Include a subtle Brazilian identity mark: a minimal Ordem e Progresso-inspired arc or ribbon in green, yellow, blue and white, integrated as an accent and not overpowering the UI.",
            "Keep the output concise and fast to render.",
            f"Theme emphasis: {variant.focus}.",
            f"Seed hint: {seed}.",
        ]
    )


def extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""
    for key in ("svg", "response", "answer", "final_answer", "result", "content", "text", "output"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str) and content.strip():
                    return content
    return ""


def sanitize_svg(raw_text: str) -> str:
    normalized = re.sub(r"```(?:svg|xml)?", "", raw_text, flags=re.IGNORECASE).replace("```", "")
    match = re.search(r"<svg[\s\S]*?</svg>", normalized, flags=re.IGNORECASE)
    if not match:
        raise ValueError("Resposta sem SVG valido")

    svg_markup = match.group(0)
    try:
        root = ET.fromstring(svg_markup)
    except ET.ParseError as exc:
        raise ValueError(f"Falha ao parsear SVG: {exc}") from exc

    forbidden = {"script", "foreignObject", "iframe", "audio", "video"}
    for node in list(root.iter()):
        tag = node.tag.split("}")[-1]
        if tag in forbidden and node is not root:
            parent = next((p for p in root.iter() if node in list(p)), None)
            if parent is not None:
                parent.remove(node)
            continue
        for attr_name in list(node.attrib):
            lower = attr_name.lower()
            value = node.attrib.get(attr_name, "")
            if lower.startswith("on"):
                del node.attrib[attr_name]
            if lower in {"href", "xlink:href"} and value.strip().lower().startswith("javascript:"):
                del node.attrib[attr_name]

    if "viewBox" not in root.attrib:
        root.set("viewBox", "0 0 1600 900")
    root.set("preserveAspectRatio", "xMidYMid slice")
    root.set("focusable", "false")
    root.set("aria-hidden", "true")

    return ET.tostring(root, encoding="unicode")


def is_svg_rich(svg_markup: str) -> bool:
    if len(svg_markup) < 4200:
        return False
    markers = (
        svg_markup.count("<path"),
        svg_markup.count("linearGradient"),
        svg_markup.count("radialGradient"),
        svg_markup.count("<circle"),
        svg_markup.count("filter"),
    )
    if sum(markers) < 14:
        return False
    if svg_markup.count("<path") < 6:
        return False
    return True


def generate_local_svg(seed: int) -> str:
    rand = random.Random(seed)
    paths: list[str] = []
    for i in range(8):
        y = 140 + i * 82 + rand.randint(-18, 18)
        amp = 32 + rand.randint(8, 44)
        p1 = 220 + rand.randint(-80, 100)
        p2 = 760 + rand.randint(-120, 120)
        p3 = 1180 + rand.randint(-140, 140)
        paths.append(
            f"<path d='M -120 {y} C {p1} {y-amp}, {p2} {y+amp}, 1720 {y-8} "
            f"C {p3} {y+amp}, {p2-180} {y-amp}, -120 {y+6} Z' fill='url(#flow{i % 4})' opacity='{0.08 + i*0.015:.3f}'/>"
        )

    rings: list[str] = []
    for _ in range(9):
        cx = rand.randint(140, 1460)
        cy = rand.randint(120, 780)
        r = rand.randint(48, 190)
        start = rand.uniform(0.15, 1.6)
        end = start + rand.uniform(1.8, 3.6)
        x1 = cx + math.cos(start) * r
        y1 = cy + math.sin(start) * r
        x2 = cx + math.cos(end) * r
        y2 = cy + math.sin(end) * r
        large = 1 if (end - start) > math.pi else 0
        rings.append(
            f"<path d='M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f}' "
            f"stroke='url(#arc)' stroke-width='{rand.uniform(1.2, 2.6):.2f}' fill='none' opacity='{rand.uniform(0.16, 0.34):.2f}'/>"
        )

    nodes = "".join(
        f"<circle cx='{rand.randint(90,1510)}' cy='{rand.randint(80,820)}' r='{rand.uniform(1.2,3.8):.2f}' fill='url(#node)' opacity='{rand.uniform(0.35,0.92):.2f}'/>"
        for _ in range(68)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" focusable="false" aria-hidden="true">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#07182c"/>
      <stop offset="100%" stop-color="#06101d"/>
    </linearGradient>
    <radialGradient id="glowA" cx="0.2" cy="0.18" r="0.48">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="#38bdf8" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowB" cx="0.84" cy="0.2" r="0.42">
      <stop offset="0%" stop-color="#22c55e" stop-opacity="0.26"/>
      <stop offset="100%" stop-color="#22c55e" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="glowC" cx="0.56" cy="0.78" r="0.50">
      <stop offset="0%" stop-color="#14b8a6" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="#14b8a6" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="flow0" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#38bdf8" stop-opacity="0.0"/><stop offset="50%" stop-color="#38bdf8" stop-opacity="0.38"/><stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/></linearGradient>
    <linearGradient id="flow1" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#22c55e" stop-opacity="0.0"/><stop offset="50%" stop-color="#22c55e" stop-opacity="0.34"/><stop offset="100%" stop-color="#22c55e" stop-opacity="0.0"/></linearGradient>
    <linearGradient id="flow2" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#facc15" stop-opacity="0.0"/><stop offset="50%" stop-color="#facc15" stop-opacity="0.28"/><stop offset="100%" stop-color="#facc15" stop-opacity="0.0"/></linearGradient>
    <linearGradient id="flow3" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#14b8a6" stop-opacity="0.0"/><stop offset="50%" stop-color="#14b8a6" stop-opacity="0.32"/><stop offset="100%" stop-color="#14b8a6" stop-opacity="0.0"/></linearGradient>
    <linearGradient id="arc" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stop-color="#38bdf8"/><stop offset="50%" stop-color="#22c55e"/><stop offset="100%" stop-color="#facc15"/></linearGradient>
    <radialGradient id="node" cx="0.5" cy="0.5" r="0.6"><stop offset="0%" stop-color="#ffffff" stop-opacity="0.95"/><stop offset="100%" stop-color="#ffffff" stop-opacity="0"/></radialGradient>
  </defs>
  <rect width="1600" height="900" fill="url(#bg)"/>
  <rect width="1600" height="900" fill="url(#glowA)"/>
  <rect width="1600" height="900" fill="url(#glowB)"/>
  <rect width="1600" height="900" fill="url(#glowC)"/>
  {''.join(paths)}
  {''.join(rings)}
  {nodes}
</svg>"""
    return svg


def _post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    req = request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "curl/8.5.0",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def call_llm(api_base: str, prompt: str, model: str, seed: int, timeout: int, ollama_base: str) -> str:
    llm_payload = {
        "prompt": prompt,
        "model": model,
        "max_rounds": 1,
        "use_native_tools": False,
        "conversation_id": f"nextcloud-background-{seed}",
    }
    last_error: Exception | None = None
    for _ in range(3):
        try:
            data = _post_json(f"{api_base.rstrip('/')}/llm-tools/chat", llm_payload, timeout)
            text = extract_text(data)
            if text.strip():
                sanitized = sanitize_svg(text)
                if is_svg_rich(sanitized):
                    return sanitized
                last_error = RuntimeError("SVG retornado com baixa complexidade visual")
                continue
            last_error = RuntimeError("API respondeu sem conteudo textual")
        except Exception as exc:
            last_error = exc

    # Fallback: Ollama direto (mesma lógica de prompt do site)
    ollama_payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.85,
            "seed": seed,
            "num_predict": 900,
        },
    }
    try:
        data = _post_json(f"{ollama_base.rstrip('/')}/api/generate", ollama_payload, timeout)
        text = extract_text(data)
        if text.strip():
            sanitized = sanitize_svg(text)
            if is_svg_rich(sanitized):
                return sanitized
            raise RuntimeError("SVG do Ollama com baixa complexidade visual")
        raise RuntimeError("Ollama respondeu sem conteudo textual")
    except Exception as exc:
        # Fallback final deterministico para manter o padrao visual, mesmo sem LLM.
        return generate_local_svg(seed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera SVG de fundo do Nextcloud no padrao RPA4All")
    parser.add_argument("--api-base", default="https://api.rpa4all.com/agents-api")
    parser.add_argument("--model", default="phi4-mini:latest")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--ollama-base", default="http://192.168.15.2:11434")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    seed = args.seed if args.seed > 0 else random.randint(100000, 999999)
    variant = random.choice(VARIANTS)
    context = resolve_context()
    prompt = build_prompt(variant, seed, context)
    svg = call_llm(args.api_base, prompt, args.model, seed, args.timeout, args.ollama_base)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")

    print(f"SVG gerado: {output}")
    print(f"Variant: {variant.variant_id} | Seed: {seed} | Contexto: {context['part_of_day']}/{context['season']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
