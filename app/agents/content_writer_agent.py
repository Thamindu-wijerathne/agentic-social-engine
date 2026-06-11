import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.llm import main_llm
from app.prompts.PromptManager import PromptManager

logger = logging.getLogger(__name__)

TEMP_CONTENT_DIR = Path(__file__).resolve().parent.parent.parent / "temp" / "content"


class ContentWriterAgent:
    def __init__(self):
        self.llm = main_llm
        self.system_prompt = PromptManager.get("agent_prompts", "content_writer_agent_system_prompt")

    def _extract_json_payload(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for start_char in ("[", "{"):
            start = text.find(start_char)
            while start != -1:
                try:
                    obj, _ = decoder.raw_decode(text[start:])
                    return obj
                except json.JSONDecodeError:
                    start = text.find(start_char, start + 1)
        return None

    def _normalize_items(
        self,
        parsed: Any,
        research_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if isinstance(parsed, dict):
            items = parsed.get("content") or parsed.get("items") or parsed.get("posts")
            if isinstance(items, list):
                parsed = items
            else:
                parsed = [parsed]

        if not isinstance(parsed, list):
            return []

        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(parsed):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            if not title:
                continue

            picture_url = str(item.get("picture_url", item.get("image_url", ""))).strip()
            if not picture_url and index < len(research_items):
                img_urls = research_items[index].get("img_urls") or []
                if img_urls:
                    picture_url = str(img_urls[0])

            entry: dict[str, Any] = {
                "title": title,
                "description": str(item.get("description", "")).strip(),
                "picture_url": picture_url,
            }
            if index < len(research_items):
                category = research_items[index].get("category")
                if category:
                    entry["category"] = category
            normalized.append(entry)
        return normalized

    @staticmethod
    def _slugify(text: str, max_len: int = 40) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug[:max_len] or "post"

    def _save_to_temp(self, items: list[dict[str, Any]]) -> dict[str, Any]:
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

        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        else:
            content = str(content)

        parsed = self._extract_json_payload(content)
        items = self._normalize_items(parsed, research_items)
        if not items:
            logger.warning("ContentWriterAgent could not parse structured output")
            return {"batch_id": None, "saved_dir": None, "manifest_path": None, "files": [], "items": []}

        result = self._save_to_temp(items)
        logger.info("ContentWriterAgent complete items=%d", len(items))
        return result
