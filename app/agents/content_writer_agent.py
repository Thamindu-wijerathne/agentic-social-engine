import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.json_utils import extract_json_payload
from app.core.llm import main_llm
from app.core.token_usage import TokenUsage, extract_usage_from_message, log_token_usage
from app.prompts.PromptManager import PromptManager

logger = logging.getLogger(__name__)

TEMP_CONTENT_DIR = Path(__file__).resolve().parent.parent.parent / "temp" / "content"

DEFAULT_CATEGORY_HASHTAGS: dict[str, list[str]] = {
    "politics": ["#USPolitics", "#BreakingNews", "#TrendingInUS", "#USNews"],
    "health": ["#USHealth", "#HealthNews", "#TrendingInUS", "#Medicare"],
    "animals": ["#AnimalNews", "#GoodNews", "#TrendingInUS", "#Wildlife"],
}


class ContentWriterAgent:
    def __init__(self):
        self.llm = main_llm
        self.system_prompt = PromptManager.get("agent_prompts", "content_writer_agent_system_prompt")
        self.last_token_usage = TokenUsage()

    @staticmethod
    def _resolve_picture_urls(item: dict[str, Any], research_item: dict[str, Any] | None) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        def add(url: Any) -> None:
            cleaned = str(url).strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                urls.append(cleaned)

        raw_urls = item.get("picture_urls")
        if isinstance(raw_urls, list):
            for url in raw_urls:
                add(url)

        add(item.get("picture_url"))
        add(item.get("image_url"))

        raw_image_urls = item.get("image_urls")
        if isinstance(raw_image_urls, list):
            for url in raw_image_urls:
                add(url)

        if research_item:
            for url in research_item.get("img_urls") or []:
                add(url)

        return urls

    @staticmethod
    def _ensure_hashtag(tag: str) -> str:
        cleaned = re.sub(r"\s+", "", str(tag).strip().lstrip("#"))
        if not cleaned:
            return ""
        return f"#{cleaned}"

    def _normalize_hashtags(
        self,
        raw: Any,
        research_item: dict[str, Any] | None,
    ) -> list[str]:
        tags: list[str] = []
        if isinstance(raw, str):
            candidates = re.split(r"[\s,]+", raw.strip())
        elif isinstance(raw, list):
            candidates = raw
        else:
            candidates = []

        seen: set[str] = set()
        for candidate in candidates:
            tag = self._ensure_hashtag(candidate)
            key = tag.lower()
            if tag and key not in seen:
                seen.add(key)
                tags.append(tag)

        if not tags and research_item:
            category = str(research_item.get("category", "")).lower()
            tags = list(DEFAULT_CATEGORY_HASHTAGS.get(category, ["#USNews", "#TrendingInUS"]))

        return tags[:8]

    def _normalize_items(
        self,
        parsed: Any,
        research_items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if isinstance(parsed, dict):
            items = parsed.get("content") or parsed.get("items") or parsed.get("posts")
            if isinstance(items, list):
                parsed = items
            else:
                parsed = [parsed]

        if not isinstance(parsed, list):
            return [], []

        normalized: list[dict[str, Any]] = []
        skipped_no_image: list[str] = []
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue

            research_item = research_items[index] if index < len(research_items) else None
            picture_urls = self._resolve_picture_urls(item, research_item)
            if not picture_urls:
                skipped_no_image.append(title)
                logger.warning("ContentWriterAgent skipped item without picture_urls title=%r", title[:80])
                continue

            entry: dict[str, Any] = {
                "title": title,
                "description": str(item.get("description", "")).strip(),
                "picture_url": picture_urls[0],
                "picture_urls": picture_urls,
                "hashtags": self._normalize_hashtags(item.get("hashtags"), research_item),
            }
            if research_item:
                category = research_item.get("category")
                if category:
                    entry["category"] = category
            normalized.append(entry)
        return normalized, skipped_no_image

    @staticmethod
    def _slugify(text: str, max_len: int = 40) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:max_len] or "post"

    def _save_to_temp(
        self,
        items: list[dict[str, Any]],
        skipped_no_image: list[str] | None = None,
    ) -> dict[str, Any]:
        batch_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        batch_dir = TEMP_CONTENT_DIR / batch_id
        batch_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[str] = []
        for index, item in enumerate(items, start=1):
            slug = self._slugify(item["title"])
            filename = f"{index:02d}-{slug}.json"
            file_path = batch_dir / filename
            file_path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_files.append(str(file_path))

        manifest = {
            "batch_id": batch_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "count": len(items),
            "items": items,
            "files": saved_files,
            "skipped_no_image": skipped_no_image or [],
        }
        manifest_path = batch_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("ContentWriterAgent saved batch=%s files=%d dir=%s", batch_id, len(saved_files), batch_dir)
        return {
            "batch_id": batch_id,
            "saved_dir": str(batch_dir),
            "manifest_path": str(manifest_path),
            "files": saved_files,
            "items": items,
            "skipped_no_image": skipped_no_image or [],
        }

    def write_content(self, research_items: list[dict[str, Any]]) -> dict[str, Any]:
        logger.info("ContentWriterAgent start items=%d", len(research_items))
        user_payload = json.dumps(research_items, ensure_ascii=False)
        response = self.llm.invoke(
            [
                ("system", self.system_prompt),
                ("user", user_payload),
            ]
        )
        self.last_token_usage = extract_usage_from_message(response) or TokenUsage()
        log_token_usage("ContentWriterAgent", self.last_token_usage)

        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            content = str(content)

        parsed = extract_json_payload(content)
        items, skipped_no_image = self._normalize_items(parsed, research_items)
        if not items:
            logger.warning(
                "ContentWriterAgent no items with picture_url parsed=%s skipped=%d",
                parsed is not None,
                len(skipped_no_image),
            )
            return {
                "batch_id": None,
                "saved_dir": None,
                "manifest_path": None,
                "files": [],
                "items": [],
                "skipped_no_image": skipped_no_image,
                "token_usage": self.last_token_usage.to_dict(),
            }

        result = self._save_to_temp(items, skipped_no_image=skipped_no_image)
        result["token_usage"] = self.last_token_usage.to_dict()
        logger.info("ContentWriterAgent complete items=%d", len(items))
        return result
