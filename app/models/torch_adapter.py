import re
from collections import Counter
from typing import Iterable, List

import torch


_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "is",
    "are",
    "for",
    "on",
    "with",
    "这",
    "那",
    "的",
    "了",
    "和",
    "是",
    "在",
    "及",
    "与",
    "并",
}


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]+", text)]


class TorchNLPAdapter:
    """Lightweight local NLP adapter with torch tensor scoring."""

    def summarize(self, text: str, max_sentences: int = 4) -> str:
        sentences = [s.strip() for s in re.split(r"[。！？!?]\s*", text) if s.strip()]
        if not sentences:
            return ""
        if len(sentences) <= max_sentences:
            return "。".join(sentences) + "。"

        all_tokens = tokenize(text)
        freq = Counter(t for t in all_tokens if t not in _STOP_WORDS)
        scores = []
        for sent in sentences:
            token_score = sum(freq.get(t, 0) for t in tokenize(sent))
            scores.append(float(token_score))

        score_tensor = torch.tensor(scores, dtype=torch.float32)
        top_k = min(max_sentences, score_tensor.numel())
        selected = torch.topk(score_tensor, k=top_k).indices.tolist()
        selected.sort()
        summary = "。".join(sentences[i] for i in selected)
        if not summary.endswith("。"):
            summary += "。"
        return summary

    def extract_keywords(self, text: str, top_k: int = 8) -> List[str]:
        tokens = [t for t in tokenize(text) if t not in _STOP_WORDS and len(t) > 1]
        if not tokens:
            return []
        freq = Counter(tokens)
        words = list(freq.keys())
        values = torch.tensor([freq[w] for w in words], dtype=torch.float32)
        k = min(top_k, values.numel())
        idx = torch.topk(values, k=k).indices.tolist()
        return [words[i] for i in idx]

    def score_overlap(self, query: str, documents: Iterable[str]) -> List[float]:
        q_tokens = set(tokenize(query))
        scores = []
        for doc in documents:
            d_tokens = set(tokenize(doc))
            if not q_tokens or not d_tokens:
                scores.append(0.0)
                continue
            overlap = len(q_tokens & d_tokens)
            denom = len(q_tokens | d_tokens)
            scores.append(float(overlap / denom))
        return scores

    def answer_from_context(self, question: str, contexts: List[str]) -> str:
        if not contexts:
            return "我在本地资料中没有检索到足够信息。你可以先导入课程文档或补充笔记。"

        scores = self.score_overlap(question, contexts)
        score_tensor = torch.tensor(scores, dtype=torch.float32)
        best_idx = int(torch.argmax(score_tensor).item())
        best_context = contexts[best_idx]
        summary = self.summarize(best_context, max_sentences=2)
        return f"基于你当前本地资料，最相关内容是：{summary}"

