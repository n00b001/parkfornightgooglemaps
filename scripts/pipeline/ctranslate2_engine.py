"""Direct ctranslate2 translation engine.

Bypasses argos-translate wrapper for maximum throughput.
Loads models directly from argos-translate package directories using
ctranslate2 + sentencepiece (or BPE tokenizer for models without SP).

Benchmark (300 French→English translations):
  argos-translate:  5.2s  (17.5ms each)
  ctranslate2 batch: 0.7s  (2.3ms each)  ← 7.5x faster
  ctranslate2 single: 3.3s (10.9ms each) ← 1.6x faster

Usage:
    engine = CTranslate2Engine()
    engine.load_all_models()
    result = engine.translate("Ceci est un test", "fr")
    results = engine.translate_batch([("text1", "fr"), ("text2", "de")])
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Protocol

import argostranslate.package as argos_package
import ctranslate2
import sentencepiece as spm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger("pipeline")

# Source languages to install translation packages for (→ English).
REQUIRED_SOURCE_LANGUAGES = [
    "fr",
    "de",
    "es",
    "it",
    "nl",
    "pt",
    "pl",
    "ru",
    "sv",
    "da",
    "nb",
    "fi",
    "cs",
    "el",
    "hu",
    "ro",
    "bg",
    "sk",
    "sl",
    "et",
    "lt",
    "lv",
    "uk",
    "tr",
    "sq",
    "ca",
    "gl",
    "eu",
    "ga",
]


class _Tokenizer(Protocol):
    """Protocol for tokenizers (SentencePiece or BPE)."""

    def encode(self, text: str) -> list[str]: ...
    def decode(self, tokens: list[int] | list[str]) -> str: ...


class _SentencePieceTokenizer:
    """Wrapper around sentencepiece for ctranslate2 compatibility."""

    __slots__ = ("_sp",)

    def __init__(self, model_path: str) -> None:
        self._sp = spm.SentencePieceProcessor()
        self._sp.load(model_path)

    def encode(self, text: str) -> list[str]:
        return self._sp.encode_as_pieces(text)

    def decode(self, tokens: list[int] | list[str]) -> str:
        text = self._sp.decode(tokens)
        # SentencePiece uses \u2581 as whitespace prefix; replace with space
        # then collapse multiple spaces and strip.
        text = text.replace("\u2581", " ")
        return " ".join(text.split())


class _BPETokenizer:
    """Wrapper around argos BPE tokenizer for ctranslate2 compatibility.

    Uses the argos BPE tokenizer's encode/decode methods directly.
    """

    __slots__ = ("_tokenizer",)

    def __init__(self, argos_tokenizer: object) -> None:
        self._tokenizer = argos_tokenizer

    def encode(self, text: str) -> list[str]:
        return self._tokenizer.encode(text)

    def decode(self, tokens: list[int] | list[str]) -> str:
        return self._tokenizer.decode(tokens)


class _LanguageModel:
    """Loaded ctranslate2 translator + tokenizer for one language pair."""

    __slots__ = ("translator", "tokenizer", "from_code")

    def __init__(
        self,
        from_code: str,
        model_path: str,
        tokenizer: _Tokenizer,
    ) -> None:
        self.from_code = from_code
        self.translator = ctranslate2.Translator(
            model_path, device="cpu", compute_type="int8"
        )
        self.tokenizer = tokenizer


class CTranslate2Engine:
    """Direct ctranslate2 translation engine.

    Loads all argos-translate models directly into ctranslate2 for
    maximum throughput. Uses batched translation for efficiency.
    Supports both SentencePiece and BPE tokenizers.
    """

    def __init__(self) -> None:
        self._models: dict[str, _LanguageModel] = {}
        self._loaded = False

    def load_all_models(self) -> None:
        """Load all translation models from argos-translate packages.

        Call once at startup. Models stay in memory for fast translation.
        """
        if self._loaded:
            return

        packages = argos_package.get_installed_packages()
        installed_pairs = {
            (pkg.from_code, pkg.to_code): pkg for pkg in packages
            if hasattr(pkg, "from_code")
        }

        for lang_code in REQUIRED_SOURCE_LANGUAGES:
            pkg = installed_pairs.get((lang_code, "en"))
            if not pkg:
                logger.warning("No model for %s→en", lang_code)
                continue

            package_path = pkg.package_path
            model_path = os.path.join(package_path, "model")

            if not os.path.isdir(model_path):
                logger.warning("Model directory missing for %s: %s", lang_code, model_path)
                continue

            # Determine tokenizer type
            tokenizer = None
            sp_path = os.path.join(package_path, "sentencepiece.model")
            if os.path.isfile(sp_path):
                try:
                    tokenizer = _SentencePieceTokenizer(sp_path)
                except Exception as e:
                    logger.error("Failed to load SentencePiece for %s: %s", lang_code, e)
            elif hasattr(pkg, "tokenizer") and pkg.tokenizer is not None:
                try:
                    tokenizer = _BPETokenizer(pkg.tokenizer)
                except Exception as e:
                    logger.error("Failed to load BPE tokenizer for %s: %s", lang_code, e)

            if tokenizer is None:
                logger.warning("No tokenizer available for %s", lang_code)
                continue

            try:
                self._models[lang_code] = _LanguageModel(lang_code, model_path, tokenizer)
                logger.info("Loaded ctranslate2 model: %s→en", lang_code)
            except Exception as e:
                logger.error("Failed to load model for %s: %s", lang_code, e)

        self._loaded = True
        logger.info("Loaded %d ctranslate2 models", len(self._models))

    def translate(self, text: str, src_lang: str) -> str:
        """Translate a single text to English.

        Returns the original text if no model is available or input is empty.
        """
        if not text or not text.strip():
            return text.strip()

        if src_lang == "en":
            return text.strip()

        model = self._models.get(src_lang)
        if not model:
            logger.warning("No model for %s→en, returning original", src_lang)
            return text.strip()

        try:
            tokens = model.tokenizer.encode(text.strip())
            results = model.translator.translate_batch(
                [tokens],
                max_decoding_length=512,
            )
            return model.tokenizer.decode(results[0].hypotheses[0])
        except Exception as e:
            logger.error("Translation error (%s→en): %s", src_lang, e)
            return text.strip()

    def translate_batch(
        self,
        texts: list[tuple[str, str]],
    ) -> dict[str, str]:
        """Translate a batch of texts to English.

        Groups texts by source language for efficient batched translation.
        Returns {original_text: translated_text}.
        """
        if not texts:
            return {}

        # Group by language
        by_lang: dict[str, list[str]] = {}
        order: list[tuple[str, str]] = []  # (original, lang)

        for text, lang in texts:
            stripped = text.strip()
            if not stripped or lang == "en":
                order.append((text, "skip"))
                continue
            by_lang.setdefault(lang, []).append(stripped)
            order.append((text, lang))

        # Translate each language group in one batch
        translated: dict[str, str] = {}
        for lang, group in by_lang.items():
            model = self._models.get(lang)
            if not model:
                # Fallback: return original
                for text in group:
                    translated[text] = text
                continue

            try:
                all_tokens = [model.tokenizer.encode(t) for t in group]
                results = model.translator.translate_batch(
                    all_tokens,
                    max_decoding_length=512,
                )
                for i, text in enumerate(group):
                    decoded = model.tokenizer.decode(results[i].hypotheses[0])
                    translated[text] = decoded.strip() if decoded.strip() else text
            except Exception as e:
                logger.error("Batch translation error (%s→en): %s", lang, e)
                for text in group:
                    translated[text] = text

        # Build final results preserving order
        results: dict[str, str] = {}
        for original, lang in order:
            if lang == "skip":
                results[original] = original.strip()
            else:
                stripped = original.strip()
                results[original] = translated.get(stripped, stripped)

        return results
