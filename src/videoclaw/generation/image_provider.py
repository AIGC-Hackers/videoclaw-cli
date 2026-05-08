"""Small resolver for drama image generator defaults."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoclaw.config import get_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageChoice:
    provider: str
    model: str


EVOLINK_GPT_IMAGE_2 = ImageChoice(provider="evolink", model="gpt-image-2")
BYTEPLUS_SEEDREAM_LITE = ImageChoice(
    provider="byteplus",
    model="seedream-5.0-lite",
)


def default_image_candidates(explicit: ImageChoice | None = None) -> list[ImageChoice]:
    """Return provider/model candidates in drama asset preference order."""
    if explicit is None:
        return [EVOLINK_GPT_IMAGE_2, BYTEPLUS_SEEDREAM_LITE]
    if explicit == EVOLINK_GPT_IMAGE_2:
        return [explicit]
    return [explicit, EVOLINK_GPT_IMAGE_2]


def _configured_candidates(choices: list[ImageChoice], cfg: Any | None = None) -> list[ImageChoice]:
    """Keep optional fallbacks only when their credentials are configured."""
    cfg = cfg or get_config()
    configured: list[ImageChoice] = []
    explicit_first = choices[0] if choices else None

    for choice in choices:
        if choice.provider == "byteplus":
            if choice == explicit_first or getattr(cfg, "byteplus_api_key", None):
                configured.append(choice)
            continue
        if choice.provider == "evolink":
            if choice == explicit_first or getattr(cfg, "evolink_api_key", None):
                configured.append(choice)
            continue
        if choice == explicit_first:
            configured.append(choice)

    return configured or choices[:1]


class ResolvedImageGenerator:
    """Image generator that tries explicit candidates in order."""

    def __init__(self, choices: list[ImageChoice]) -> None:
        if not choices:
            raise ValueError("At least one image provider candidate is required.")
        self.choices = choices
        self.last_image_url: str | None = None
        self._generators: dict[ImageChoice, Any] = {}

    async def generate(
        self,
        prompt: str,
        *,
        output_dir: Path,
        filename: str,
        **kwargs: Any,
    ) -> Path:
        last_error: Exception | None = None

        for choice in self.choices:
            try:
                generator = self._generator_for(choice)
                provider_kwargs = dict(kwargs)
                provider_kwargs.setdefault("model", choice.model)
                path = await generator.generate(
                    prompt,
                    output_dir=output_dir,
                    filename=filename,
                    **provider_kwargs,
                )
                self.last_image_url = getattr(generator, "last_image_url", None)
                return path
            except Exception as exc:
                last_error = exc
                if choice == self.choices[-1]:
                    break
                logger.warning(
                    "Image provider %s:%s failed for %s; trying next candidate: %s",
                    choice.provider,
                    choice.model,
                    filename,
                    exc,
                )

        raise last_error or RuntimeError(f"Image generation failed for {filename}")

    def _generator_for(self, choice: ImageChoice) -> Any:
        if choice not in self._generators:
            self._generators[choice] = _build_generator(choice)
        return self._generators[choice]


def resolve_image_generator(
    *,
    image_provider: str | None = None,
    image_model: str | None = None,
) -> ResolvedImageGenerator:
    cfg = get_config()
    explicit = _explicit_choice(image_provider=image_provider, image_model=image_model)
    if explicit is None:
        explicit = _config_default_choice(cfg)
    choices = _configured_candidates(default_image_candidates(explicit), cfg)
    return ResolvedImageGenerator(choices)


def _config_default_choice(cfg: Any) -> ImageChoice | None:
    provider = getattr(cfg, "default_image_provider", None)
    model = getattr(cfg, "default_image_model", None)
    if provider == "byteplus" and model == EVOLINK_GPT_IMAGE_2.model:
        model = None
    choice = _explicit_choice(image_provider=provider, image_model=model)
    if choice == EVOLINK_GPT_IMAGE_2:
        return None
    return choice


def _explicit_choice(
    *,
    image_provider: str | None,
    image_model: str | None,
) -> ImageChoice | None:
    if not image_provider and not image_model:
        return None

    provider = (image_provider or "evolink").strip().lower()
    if provider == "evolink":
        model = image_model or EVOLINK_GPT_IMAGE_2.model
    elif provider == "byteplus":
        model = image_model or BYTEPLUS_SEEDREAM_LITE.model
    else:
        model = image_model or ""
    return ImageChoice(provider=provider, model=model)


def _build_generator(choice: ImageChoice) -> Any:
    if choice.provider == "evolink":
        from videoclaw.generation.evolink_image import EvolinkImageGenerator

        return EvolinkImageGenerator()
    if choice.provider == "byteplus":
        from videoclaw.generation.byteplus_image import BytePlusImageGenerator

        return BytePlusImageGenerator(model=choice.model)
    raise ValueError(f"Unsupported image provider: {choice.provider}")
