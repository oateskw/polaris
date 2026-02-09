"""Prompts for AI content generation focused on tech/software."""

BRAND_CONTEXT = """You are creating content for "Polaris Innovations", a tech and software brand.

Brand Voice:
- Professional yet approachable
- Innovative and forward-thinking
- Educational and helpful
- Enthusiastic about technology without being overly hyped

Target Audience:
- Software developers and engineers
- Tech enthusiasts
- Startup founders and entrepreneurs
- IT professionals
- Tech-curious business professionals

Content Themes:
- Software development best practices
- New technology trends and innovations
- Developer tools and productivity
- AI and machine learning
- Cloud computing and DevOps
- Open source software
- Tech industry insights
- Coding tips and tutorials
"""

CAPTION_GENERATION_PROMPT = """Based on the following topic, create an engaging Instagram caption for Polaris Innovations.

{brand_context}

Topic: {topic}

Additional context (if provided): {context}

Requirements:
- Keep the caption between 100-200 words
- Start with a hook that grabs attention
- Include a call-to-action (CTA) at the end
- Use line breaks for readability
- Be informative yet conversational
- Avoid excessive use of emojis (1-3 max)
- Do NOT include hashtags in the caption (they will be added separately)

Return ONLY the caption text, nothing else."""

HASHTAG_GENERATION_PROMPT = """Generate relevant Instagram hashtags for a post about the following topic.

Topic: {topic}
Caption summary: {caption_summary}

{brand_context}

Requirements:
- Generate exactly 15-20 hashtags
- Mix of popular (1M+ posts), medium (100K-1M), and niche (<100K) hashtags
- Include brand-related hashtags like #PolarisInnovations
- Focus on tech, software, and development hashtags
- Start each hashtag with #
- Separate hashtags with spaces

Return ONLY the hashtags, one space between each, nothing else."""

CONTENT_IDEAS_PROMPT = """Generate {count} unique Instagram post ideas for Polaris Innovations.

{brand_context}

Focus areas (if specified): {focus_areas}

For each idea, provide:
1. A catchy title/hook (10 words max)
2. Brief description of the post content (2-3 sentences)
3. Suggested media type (image, carousel, video/reel)
4. Key message or takeaway

Format each idea as:
---
Title: [title]
Description: [description]
Media Type: [type]
Key Message: [message]
---

Be creative and varied. Include educational content, industry insights, tips, and engagement-focused posts."""

IMPROVE_CAPTION_PROMPT = """Improve the following Instagram caption for Polaris Innovations.

{brand_context}

Original caption:
{original_caption}

Improvement focus: {improvement_focus}

Requirements:
- Maintain the core message
- Improve engagement potential
- Keep between 100-200 words
- Ensure it matches our brand voice
- Do NOT include hashtags

Return ONLY the improved caption, nothing else."""

ENGAGEMENT_RESPONSE_PROMPT = """Generate a friendly response to this Instagram comment for Polaris Innovations.

{brand_context}

Comment: {comment}
Context about the post: {post_context}

Requirements:
- Be friendly and professional
- Address the commenter directly if they asked a question
- Keep response under 50 words
- Encourage further engagement when appropriate
- Avoid generic responses

Return ONLY the response text, nothing else."""
