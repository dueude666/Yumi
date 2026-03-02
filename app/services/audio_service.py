import csv
import io
import json
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch

from app.models.torch_adapter import TorchNLPAdapter
from app.rag.repository import add_material_text
from app.services.glossary_service import apply_glossary, list_terms

_ASR_PIPELINE = None
_ASR_MODEL_ID = None


def _to_mono_16k(file_bytes: bytes, suffix: str = ".wav") -> Tuple[torch.Tensor, int]:
    try:
        import torchaudio  # type: ignore
    except ImportError as exc:
        raise RuntimeError("torchaudio is required for audio processing.") from exc

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    waveform, sample_rate = torchaudio.load(tmp_path)
    try:
        Path(tmp_path).unlink(missing_ok=True)
    except OSError:
        pass

    if waveform.ndim != 2 or waveform.numel() == 0:
        raise RuntimeError("invalid audio waveform")
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sample_rate != 16000:
        waveform = torchaudio.functional.resample(waveform, sample_rate, 16000)
        sample_rate = 16000
    return waveform, sample_rate


def _get_asr_pipeline(model_id: str = "openai/whisper-small", local_only: bool = False):
    global _ASR_PIPELINE, _ASR_MODEL_ID
    if _ASR_PIPELINE is not None and _ASR_MODEL_ID == model_id:
        return _ASR_PIPELINE

    try:
        from transformers import pipeline  # type: ignore
    except ImportError as exc:
        raise RuntimeError("transformers is required for ASR.") from exc

    try:
        _ASR_PIPELINE = pipeline(
            task="automatic-speech-recognition",
            model=model_id,
            device=-1,
            model_kwargs={"local_files_only": local_only},
        )
    except Exception as exc:  # pylint: disable=broad-except
        raise RuntimeError(f"failed to load ASR model '{model_id}': {exc}") from exc

    _ASR_MODEL_ID = model_id
    return _ASR_PIPELINE


def _simple_kmeans_2(features: torch.Tensor, steps: int = 15) -> torch.Tensor:
    if features.shape[0] < 2:
        return torch.zeros(features.shape[0], dtype=torch.long)

    idx_min = int(torch.argmin(features[:, 0]).item())
    idx_max = int(torch.argmax(features[:, 0]).item())
    centers = torch.stack([features[idx_min], features[idx_max]], dim=0)

    for _ in range(steps):
        distances = torch.cdist(features, centers)
        labels = torch.argmin(distances, dim=1)
        new_centers = []
        for cid in range(2):
            group = features[labels == cid]
            if group.numel() == 0:
                new_centers.append(centers[cid])
            else:
                new_centers.append(group.mean(dim=0))
        next_centers = torch.stack(new_centers, dim=0)
        if torch.allclose(next_centers, centers, atol=1e-4):
            break
        centers = next_centers
    return labels


def _frame_features(signal: torch.Tensor, sample_rate: int) -> Tuple[torch.Tensor, List[Tuple[float, float]]]:
    frame_size = int(sample_rate * 2.0)
    hop = int(sample_rate * 1.0)
    total = signal.shape[-1]
    if total < frame_size:
        frame = torch.nn.functional.pad(signal, (0, frame_size - total))
        return _compute_feature_tensor([frame], sample_rate), [(0.0, total / sample_rate)]

    frames = []
    spans = []
    start = 0
    while start + frame_size <= total:
        end = start + frame_size
        frames.append(signal[..., start:end])
        spans.append((start / sample_rate, end / sample_rate))
        start += hop
    return _compute_feature_tensor(frames, sample_rate), spans


def _compute_feature_tensor(frames: Sequence[torch.Tensor], sample_rate: int) -> torch.Tensor:
    feat_list: List[torch.Tensor] = []
    for frame in frames:
        x = frame.squeeze(0).float()
        energy = torch.mean(torch.abs(x)) + 1e-8
        zcr = torch.mean((x[:-1] * x[1:] < 0).float()) if x.numel() > 1 else torch.tensor(0.0)
        spec = torch.fft.rfft(x)
        mag = torch.abs(spec)
        if mag.numel() == 0:
            centroid = torch.tensor(0.0)
        else:
            freqs = torch.linspace(0, sample_rate / 2, mag.shape[0])
            centroid = (mag * freqs).sum() / (mag.sum() + 1e-8)
        feat_list.append(
            torch.tensor(
                [
                    float(torch.log10(energy + 1e-8)),
                    float(zcr),
                    float(centroid / max(sample_rate, 1)),
                ],
                dtype=torch.float32,
            )
        )
    if not feat_list:
        return torch.zeros((0, 3), dtype=torch.float32)
    return torch.stack(feat_list, dim=0)


def _diarize_simple(signal: torch.Tensor, sample_rate: int) -> List[Dict[str, Any]]:
    features, spans = _frame_features(signal, sample_rate)
    if features.shape[0] == 0:
        return []

    energy = features[:, 0]
    threshold = torch.quantile(energy, 0.35).item()
    active_mask = energy >= threshold
    if int(active_mask.sum().item()) < 2:
        return [{"speaker": "Speaker A", "start": 0.0, "end": float(signal.shape[-1] / sample_rate)}]

    active_features = features[active_mask]
    active_spans = [span for span, m in zip(spans, active_mask.tolist()) if m]
    labels = _simple_kmeans_2(active_features)

    segments: List[Dict[str, Any]] = []
    for idx, span in enumerate(active_spans):
        speaker = "Speaker A" if int(labels[idx].item()) == 0 else "Speaker B"
        start, end = span
        if segments and segments[-1]["speaker"] == speaker and math.isclose(segments[-1]["end"], start, abs_tol=0.2):
            segments[-1]["end"] = end
        else:
            segments.append({"speaker": speaker, "start": start, "end": end})
    return segments


def _normalize_asr_chunks(asr_result: Dict[str, Any], duration_s: float) -> List[Dict[str, Any]]:
    chunks = asr_result.get("chunks")
    if not chunks:
        return [
            {
                "text": asr_result.get("text", ""),
                "timestamp": (0.0, duration_s),
            }
        ]

    normalized = []
    for chunk in chunks:
        ts = chunk.get("timestamp", (None, None))
        if isinstance(ts, tuple):
            start = 0.0 if ts[0] is None else float(ts[0])
            end = duration_s if ts[1] is None else float(ts[1])
        else:
            start, end = 0.0, duration_s
        normalized.append({"text": chunk.get("text", "").strip(), "timestamp": (start, end)})
    return normalized


def _attach_speaker(
    chunks: List[Dict[str, Any]], diar_segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    if not diar_segments:
        return [{"speaker": "Speaker A", "text": " ".join(c["text"] for c in chunks).strip(), "start": 0.0, "end": chunks[-1]["timestamp"][1] if chunks else 0.0}]

    merged: List[Dict[str, Any]] = []
    for chunk in chunks:
        start, end = chunk["timestamp"]
        mid = (start + end) / 2.0
        speaker = "Speaker A"
        for seg in diar_segments:
            if seg["start"] <= mid <= seg["end"]:
                speaker = seg["speaker"]
                break

        text = chunk["text"].strip()
        if not text:
            continue
        if merged and merged[-1]["speaker"] == speaker:
            merged[-1]["text"] = (merged[-1]["text"] + " " + text).strip()
            merged[-1]["end"] = end
        else:
            merged.append({"speaker": speaker, "text": text, "start": start, "end": end})
    return merged


def _build_structured_notes(text: str, summary: str, keywords: List[str], glossary_hits: List[Dict[str, str]]) -> Dict[str, Any]:
    sentences = [s.strip() for s in text.replace("\n", " ").split("。") if s.strip()]
    action_signals = ("作业", "截止", "deadline", "exam", "考试", "注意", "实验")
    action_items = [s for s in sentences if any(sig.lower() in s.lower() for sig in action_signals)]

    return {
        "summary": summary,
        "key_points": keywords[:10],
        "action_items": action_items[:8],
        "glossary_hits": glossary_hits,
    }


def _build_flashcards(text: str, keywords: List[str], course_name: str = "course") -> List[Dict[str, str]]:
    sentences = [s.strip() for s in text.replace("\n", " ").split("。") if s.strip()]
    cards: List[Dict[str, str]] = []
    for kw in keywords[:20]:
        related = next((s for s in sentences if kw in s), "")
        back = related if related else f"{kw} is a key concept in this lecture."
        cards.append(
            {
                "front": f"What does '{kw}' refer to?",
                "back": back,
                "tags": f"yumi::{course_name}",
            }
        )
    return cards


def _cards_to_csv(cards: List[Dict[str, str]]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Front", "Back", "Tags"])
    for card in cards:
        writer.writerow([card["front"], card["back"], card["tags"]])
    return output.getvalue()


def process_audio_upload(
    conn: Any,
    course_id: int,
    source_name: str,
    filename: str,
    file_bytes: bytes,
    language: Optional[str] = None,
    diarize: bool = True,
    model_id: str = "openai/whisper-small",
    local_only: bool = False,
) -> Dict[str, Any]:
    suffix = Path(filename).suffix or ".wav"
    waveform, sample_rate = _to_mono_16k(file_bytes=file_bytes, suffix=suffix)
    duration_s = float(waveform.shape[-1] / max(sample_rate, 1))

    asr = _get_asr_pipeline(model_id=model_id, local_only=local_only)
    asr_input = {"array": waveform.squeeze(0).numpy(), "sampling_rate": sample_rate}
    asr_kwargs: Dict[str, Any] = {"return_timestamps": True}
    if language:
        asr_kwargs["generate_kwargs"] = {"language": language}

    try:
        asr_result = asr(asr_input, **asr_kwargs)
    except Exception as exc:  # pylint: disable=broad-except
        raise RuntimeError(f"ASR failed: {exc}") from exc

    raw_text = str(asr_result.get("text", "")).strip()
    if not raw_text:
        raise RuntimeError("ASR returned empty text")

    glossary_terms = list_terms(conn)
    normalized_text, glossary_hits = apply_glossary(raw_text, glossary_terms)

    diar_segments = _diarize_simple(waveform, sample_rate) if diarize else []
    chunks = _normalize_asr_chunks(asr_result, duration_s)
    speaker_segments = _attach_speaker(chunks, diar_segments)

    adapter = TorchNLPAdapter()
    summary = adapter.summarize(normalized_text, max_sentences=5)
    keywords = adapter.extract_keywords(normalized_text, top_k=18)
    structured_notes = _build_structured_notes(normalized_text, summary, keywords, glossary_hits)

    course_row = conn.execute("SELECT name FROM courses WHERE id = ?", (course_id,)).fetchone()
    course_name = course_row["name"] if course_row else "course"
    flashcards = _build_flashcards(normalized_text, keywords, course_name=course_name)

    cursor = conn.execute(
        """
        INSERT INTO transcripts (
            course_id, source_name, language, raw_text, normalized_text, summary,
            structured_notes, speaker_segments, glossary_hits, flashcards
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            course_id,
            source_name,
            language or "",
            raw_text,
            normalized_text,
            summary,
            json.dumps(structured_notes, ensure_ascii=False),
            json.dumps(speaker_segments, ensure_ascii=False),
            json.dumps(glossary_hits, ensure_ascii=False),
            json.dumps(flashcards, ensure_ascii=False),
        ),
    )
    transcript_id = int(cursor.lastrowid)

    add_material_text(
        conn=conn,
        course_id=course_id,
        source_name=source_name,
        text=normalized_text,
        page_number=None,
    )
    conn.commit()

    return {
        "transcript_id": transcript_id,
        "course_id": course_id,
        "source_name": source_name,
        "filename": filename,
        "duration_seconds": round(duration_s, 2),
        "summary": summary,
        "structured_notes": structured_notes,
        "speaker_segments": speaker_segments,
        "glossary_hits": glossary_hits,
        "flashcard_count": len(flashcards),
    }


def list_transcripts(conn: Any, course_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    if course_id is None:
        rows = conn.execute(
            """
            SELECT t.id, t.course_id, c.name AS course_name, t.source_name, t.language, t.summary, t.created_at
            FROM transcripts t
            JOIN courses c ON c.id = t.course_id
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT t.id, t.course_id, c.name AS course_name, t.source_name, t.language, t.summary, t.created_at
            FROM transcripts t
            JOIN courses c ON c.id = t.course_id
            WHERE t.course_id = ?
            ORDER BY t.created_at DESC
            LIMIT ?
            """,
            (course_id, limit),
        ).fetchall()

    return [
        {
            "transcript_id": int(row["id"]),
            "course_id": int(row["course_id"]),
            "course_name": row["course_name"],
            "source_name": row["source_name"],
            "language": row["language"],
            "summary": row["summary"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def export_anki_csv(conn: Any, transcript_id: int) -> str:
    row = conn.execute(
        "SELECT flashcards FROM transcripts WHERE id = ?",
        (transcript_id,),
    ).fetchone()
    if not row:
        raise RuntimeError("transcript not found")
    cards = json.loads(row["flashcards"])
    if not isinstance(cards, list):
        raise RuntimeError("flashcards data invalid")
    return _cards_to_csv(cards)

