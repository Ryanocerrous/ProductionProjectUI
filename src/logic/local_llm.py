from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class LlmClassification:
    category: str
    suspicion_score: int
    rationale: str
    raw_output: str
    parsed_json: dict[str, Any] | None
    command: list[str]
    returncode: int
    stderr: str


@dataclass(slots=True)
class LlmGeneration:
    raw_output: str
    command: list[str]
    returncode: int
    stderr: str


def build_classification_prompt(text: str) -> str:
    return (
        "You are a forensic triage assistant.\n"
        "Classify the following text.\n"
        "Return JSON only (no markdown, no extra text) with fields:\n"
        "- category\n"
        "- suspicion_score (0-100)\n"
        "- rationale\n\n"
        "TEXT:\n"
        f"{text.strip()}\n"
    )


def classify_text_with_llama(
    text: str,
    cfg: dict[str, Any],
    prompt: str | None = None,
) -> LlmClassification:
    if not text.strip():
        raise ValueError("No text provided for LLM classification.")

    final_prompt = prompt if prompt is not None else build_classification_prompt(text)
    generation = generate_text_with_llama(final_prompt, cfg)
    stdout = generation.raw_output
    stderr = generation.stderr
    parsed = _extract_json_object(stdout)
    category = "unknown"
    suspicion_score = 0
    rationale = "No JSON found in model output."
    if parsed is not None:
        category = str(parsed.get("category", "unknown")).strip() or "unknown"
        suspicion_score = _coerce_score(parsed.get("suspicion_score", 0))
        rationale = str(parsed.get("rationale", "")).strip() or rationale
    elif stdout:
        rationale = stdout[:400]

    return LlmClassification(
        category=category,
        suspicion_score=suspicion_score,
        rationale=rationale,
        raw_output=stdout,
        parsed_json=parsed,
        command=generation.command,
        returncode=int(generation.returncode),
        stderr=stderr,
    )


def generate_text_with_llama(prompt: str, cfg: dict[str, Any]) -> LlmGeneration:
    if not prompt.strip():
        raise ValueError("Prompt is empty.")

    llm_cfg = dict((cfg.get("llm") or {}))
    binary = str(llm_cfg.get("binary", "")).strip()
    model = str(llm_cfg.get("model", "")).strip()
    if not binary or not model:
        raise ValueError("Missing llm.binary or llm.model in config.")

    binary_path = str(Path(binary).expanduser())
    model_path = str(Path(model).expanduser())
    if not Path(binary_path).exists():
        raise FileNotFoundError(f"llm.binary not found: {binary_path}")
    if not Path(model_path).exists():
        raise FileNotFoundError(f"llm.model not found: {model_path}")

    temp = float(llm_cfg.get("temperature", 0.2))
    ctx = int(llm_cfg.get("context_tokens", 256))
    max_tokens = int(llm_cfg.get("max_tokens", 96))
    threads = int(llm_cfg.get("threads", 2))
    gpu_layers = int(llm_cfg.get("gpu_layers", 0))
    timeout_s = float(llm_cfg.get("timeout_s", 120))

    cmd = [
        binary_path,
        "-m",
        model_path,
        "-p",
        prompt,
        "--temp",
        str(temp),
        "-c",
        str(ctx),
        "-n",
        str(max_tokens),
        "-t",
        str(threads),
        "-ngl",
        str(gpu_layers),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"llama-cli timed out after {timeout_s:.1f}s") from exc

    return LlmGeneration(
        raw_output=(proc.stdout or "").strip(),
        command=cmd,
        returncode=int(proc.returncode),
        stderr=(proc.stderr or "").strip(),
    )


def _coerce_score(value: Any) -> int:
    try:
        score = int(float(value))
    except Exception:
        return 0
    return max(0, min(100, score))


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    start = stripped.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : idx + 1]
                try:
                    parsed = json.loads(candidate)
                except Exception:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None
