import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PromptManager:

    @classmethod
    def get(cls, section: str, name: str) -> str:
        base_dir = Path(__file__).resolve().parent
        prompt_path = base_dir / section / f"{name}.txt"
        logger.debug("Loading prompt path=%s", prompt_path)

        if not prompt_path.exists():
            logger.error("Prompt not found path=%s", prompt_path)
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        text = prompt_path.read_text(encoding="utf-8")
        logger.info("Prompt loaded section=%s name=%s chars=%d", section, name, len(text))
        return text
