"""AI-powered lead conversation responder."""

import logging
from typing import Optional

from polaris.services.ai.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a friendly, knowledgeable assistant representing a company that offers AI automation solutions for small businesses. Your goal is to qualify leads and guide them toward booking a discovery call.

About our product:
- We help small business owners automate repetitive tasks using AI agents
- Use cases: lead follow-up, appointment booking, inquiry handling, customer support
- We offer a free 20-minute discovery call to assess fit

Your conversation style:
- Warm and conversational, NOT salesy or pushy
- Ask about their current pain points and workflows
- Listen and empathize before pitching
- Answer questions honestly and concisely
- When the prospect seems engaged or has a clear pain point, naturally suggest a discovery call or offer a free resource

Rules:
- Keep replies short (2-4 sentences max for DM context)
- Never use bullet points or formal lists — write naturally
- Do not repeat yourself or rehash the same talking points
- If they seem uninterested, gracefully close the conversation
- You are replying via Instagram DM, so be informal and human"""


class LeadResponder:
    """Generates AI replies for lead conversations using Claude."""

    def __init__(self, claude_client: Optional[ClaudeClient] = None):
        self.claude = claude_client or ClaudeClient()

    def generate_reply(
        self,
        commenter_username: str,
        conversation_history: list[dict],
        post_topic: Optional[str] = None,
    ) -> str:
        """Generate a contextual reply for a lead conversation.

        Args:
            commenter_username: The lead's Instagram username
            conversation_history: List of dicts with keys: role, message, timestamp
                role is either 'assistant' or 'user'
            post_topic: Optional topic of the original post that triggered the lead

        Returns:
            Reply text to send as a DM
        """
        # Build message list for multi-turn context
        messages = []

        if post_topic:
            context_note = (
                f"This person ({commenter_username}) originally commented on a post about: {post_topic}. "
                "Use this as natural context for the conversation."
            )
            messages.append({"role": "user", "content": context_note})
            messages.append({
                "role": "assistant",
                "content": "Understood, I'll keep the post topic in mind as context for this conversation.",
            })

        for entry in conversation_history:
            role = entry.get("role", "user")
            content = entry.get("message", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        if not messages:
            logger.warning("generate_reply called with empty conversation history")
            return ""

        try:
            reply = self.claude.generate_with_context(
                messages=messages,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=300,
                temperature=0.8,
            )
            return reply.strip()
        except Exception as e:
            logger.error(f"Failed to generate lead reply: {e}")
            raise
