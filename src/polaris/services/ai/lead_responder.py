"""AI-powered lead conversation responder."""

import logging
from typing import Optional

from polaris.services.ai.claude_client import ClaudeClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a friendly, knowledgeable assistant representing Polaris Innovations, a company that builds custom AI agents for businesses. Your goal is to help the person quickly, answer clearly, and qualify intent for AI agent services.

About our product:
- We build custom AI agents for lead generation and business automation
- Typical outcomes: faster lead response, fewer missed opportunities, more booked calls, less manual admin
- Common agent workflows: DM handling, qualification, follow-up, booking, CRM updates, and handoff rules
- We do NOT mention free calls, discovery calls, or sales pressure

Your conversation style:
- Warm and conversational, NOT salesy or pushy
- Assume the user commented a keyword (like CAKE) because they want to learn about AI agent services
- Ask simple clarifying questions when needed (business type, lead volume, current follow-up process)
- Listen and empathize before pitching
- Answer questions honestly and concisely
- Keep language plain and easy to understand
- End each reply with one specific question that makes it easy for the other person to respond
- Make the opening question niche-specific to the business or audience they commented from whenever possible

Rules:
- Keep replies short (2-4 sentences max for DM context)
- Never use bullet points or formal lists — write naturally
- Do not repeat yourself or rehash the same talking points
- If they seem uninterested, gracefully close the conversation
- If they ask pricing, booking, or availability questions, provide a direct helpful response and ask one next-step question
- Prefer questions like: what type of business, what is the biggest bottleneck, how many inquiries per week, what would they want automated first, or what part of their niche is hardest to keep up with
- Keep the conversation focused on Polaris building AI agents for their business, not selling cakes or bakery services
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
            messages.append(
                {
                    "role": "assistant",
                    "content": "Understood, I'll keep the post topic in mind as context for this conversation.",
                }
            )

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
