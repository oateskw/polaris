"""AI-powered content generation for Instagram."""

from dataclasses import dataclass
from typing import Optional

from polaris.services.ai.claude_client import ClaudeClient
from polaris.services.ai.prompts import (
    BRAND_CONTEXT,
    CAPTION_GENERATION_PROMPT,
    CONTENT_IDEAS_PROMPT,
    HASHTAG_GENERATION_PROMPT,
    IMPROVE_CAPTION_PROMPT,
)


@dataclass
class GeneratedCaption:
    """Generated caption with metadata."""

    caption: str
    hashtags: str
    topic: str
    ai_model: str


@dataclass
class ContentIdea:
    """A content idea for Instagram."""

    title: str
    description: str
    media_type: str
    key_message: str


class ContentGenerator:
    """Generate Instagram content using Claude AI."""

    def __init__(self, client: Optional[ClaudeClient] = None):
        self.client = client or ClaudeClient()

    def generate_caption(
        self,
        topic: str,
        context: Optional[str] = None,
    ) -> GeneratedCaption:
        """Generate a caption for an Instagram post.

        Args:
            topic: The topic or subject of the post
            context: Additional context or requirements

        Returns:
            GeneratedCaption with caption, hashtags, and metadata
        """
        # Generate caption
        caption_prompt = CAPTION_GENERATION_PROMPT.format(
            brand_context=BRAND_CONTEXT,
            topic=topic,
            context=context or "None provided",
        )

        caption = self.client.generate(
            prompt=caption_prompt,
            temperature=0.7,
        ).strip()

        # Generate hashtags
        hashtags = self.generate_hashtags(topic, caption[:200])

        return GeneratedCaption(
            caption=caption,
            hashtags=hashtags,
            topic=topic,
            ai_model=self.client.DEFAULT_MODEL,
        )

    def generate_hashtags(
        self,
        topic: str,
        caption_summary: Optional[str] = None,
    ) -> str:
        """Generate hashtags for a post.

        Args:
            topic: The topic of the post
            caption_summary: Summary of the caption for context

        Returns:
            String of hashtags separated by spaces
        """
        prompt = HASHTAG_GENERATION_PROMPT.format(
            topic=topic,
            caption_summary=caption_summary or topic,
            brand_context=BRAND_CONTEXT,
        )

        hashtags = self.client.generate(
            prompt=prompt,
            temperature=0.5,
            max_tokens=200,
        ).strip()

        # Ensure hashtags are properly formatted
        tags = hashtags.split()
        formatted_tags = []
        for tag in tags:
            tag = tag.strip()
            if tag and not tag.startswith("#"):
                tag = f"#{tag}"
            if tag:
                formatted_tags.append(tag)

        return " ".join(formatted_tags)

    def generate_content_ideas(
        self,
        count: int = 5,
        focus_areas: Optional[list[str]] = None,
    ) -> list[ContentIdea]:
        """Generate content ideas for Instagram posts.

        Args:
            count: Number of ideas to generate
            focus_areas: Optional list of topics to focus on

        Returns:
            List of ContentIdea objects
        """
        focus_str = ", ".join(focus_areas) if focus_areas else "General tech and software topics"

        prompt = CONTENT_IDEAS_PROMPT.format(
            count=count,
            brand_context=BRAND_CONTEXT,
            focus_areas=focus_str,
        )

        response = self.client.generate(
            prompt=prompt,
            temperature=0.8,
            max_tokens=2000,
        )

        return self._parse_content_ideas(response)

    def improve_caption(
        self,
        original_caption: str,
        improvement_focus: str = "engagement and clarity",
    ) -> str:
        """Improve an existing caption.

        Args:
            original_caption: The caption to improve
            improvement_focus: What aspect to focus on improving

        Returns:
            Improved caption text
        """
        prompt = IMPROVE_CAPTION_PROMPT.format(
            brand_context=BRAND_CONTEXT,
            original_caption=original_caption,
            improvement_focus=improvement_focus,
        )

        return self.client.generate(
            prompt=prompt,
            temperature=0.6,
        ).strip()

    def _parse_content_ideas(self, response: str) -> list[ContentIdea]:
        """Parse content ideas from AI response."""
        ideas = []
        current_idea: dict[str, str] = {}

        for line in response.split("\n"):
            line = line.strip()

            if line.startswith("---"):
                if current_idea and "title" in current_idea:
                    ideas.append(ContentIdea(
                        title=current_idea.get("title", ""),
                        description=current_idea.get("description", ""),
                        media_type=current_idea.get("media_type", "image"),
                        key_message=current_idea.get("key_message", ""),
                    ))
                current_idea = {}
            elif line.lower().startswith("title:"):
                current_idea["title"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("description:"):
                current_idea["description"] = line.split(":", 1)[1].strip()
            elif line.lower().startswith("media type:"):
                current_idea["media_type"] = line.split(":", 1)[1].strip().lower()
            elif line.lower().startswith("key message:"):
                current_idea["key_message"] = line.split(":", 1)[1].strip()

        # Add last idea if present
        if current_idea and "title" in current_idea:
            ideas.append(ContentIdea(
                title=current_idea.get("title", ""),
                description=current_idea.get("description", ""),
                media_type=current_idea.get("media_type", "image"),
                key_message=current_idea.get("key_message", ""),
            ))

        return ideas
