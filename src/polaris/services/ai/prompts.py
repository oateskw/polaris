"""Prompts for AI content generation - Polaris Innovations mid-market AI brand."""

BRAND_CONTEXT = """You are creating content for "Polaris Innovations", an AI operations firm that builds practical systems for growing businesses.

Brand Voice:
- Plain, direct, and easy to understand
- Confident but human; explain things in everyday language
- Focus on practical outcomes and real examples
- No buzzwords, no fluff, no jargon-heavy wording
- Sound like an experienced operator talking to another operator

Target Audience:
- Founders and operators of $2M-$10M companies
- Ops leaders and owners dealing with messy handoffs and disconnected tools
- Teams that outgrew manual processes and need clear systems
- Decision-makers with budget ($10k-$50k projects) evaluating firms

Core Problems We Solve:
- Teams are scaling but systems are not
- Data is spread across tools and hard to trust
- Work breaks when one person is out
- Companies keep hiring to patch broken process
- AI tools add complexity without clear workflows

Positioning:
- We build the system the company runs on, not just a bot
- We connect tools, clean data flow, and define clear handoffs
- We price for outcomes: $10k-$50k projects and long-term support
- We focus on companies too complex for off-the-shelf fixes

Content Themes:
- Simple breakdowns of what was broken and what fixed it
- Why implementations fail when tools are not connected
- What companies at the $2M-$10M stage need to systematize
- Clear process decisions and practical tradeoffs
- Real outcomes: fewer errors, faster response times, better follow-up

Tone Examples:
- "Most teams do not have an AI issue. They have a process issue."
- "If your tools do not connect, your team slows down every day."
- "A $4M company cannot run on memory and spreadsheets forever."
- "We build the workflow your team can trust when volume grows."
- "The winners are not using more tools. They are using cleaner systems."
"""

CAPTION_GENERATION_PROMPT = """Write an Instagram caption for Polaris Innovations — an AI operations firm serving $2M-$10M companies.

{brand_context}

Topic: {topic}

Additional context (if provided): {context}

Requirements:
- Use plain language a non-technical owner can understand on first read
- Write like you're talking to a busy local business owner, not a consultant
- If a role is provided in context (chef, owner, founder), mention that role directly in the first line
- Keep each sentence short and direct
- Explain one main idea only; do not stack too many points
- Avoid technical jargon unless absolutely needed, and explain it in simple words
- Prefer everyday words: messages, inquiries, bookings, orders, calendar, follow-up
- Avoid consultant wording like: lead generation, qualify leads, pipeline optimization, operational infrastructure
- Do not mention "free 30-minute discovery call" or similar discovery-call offers
- End with a simple CTA for action (DM or save)
- Target 25-45 words
- Hard maximum 60 words
- No emojis
- No hashtags (added separately)

Return ONLY the caption text, nothing else."""

HASHTAG_GENERATION_PROMPT = """Generate high-performing Instagram hashtags for a Polaris Innovations post targeting mid-market operators and founders.

Topic: {topic}
Caption summary: {caption_summary}

{brand_context}

Requirements:
- Generate exactly 15-20 hashtags
- Mix of reach sizes:
  - 3-4 broad reach (1M+ posts): #BusinessOperations, #Entrepreneur, #BusinessGrowth, #AIStrategy
  - 6-8 medium reach (100K-500K): mid-market, operations, scaling, B2B, AI implementation topics
  - 4-6 targeted niche (<100K): specific to operational infrastructure, systems design, mid-market AI, B2B automation
- Include #PolarisInnovations
- Focus on: operational excellence, systems thinking, B2B AI, scaling companies, mid-market challenges
- Avoid solopreneur/freelancer hashtags (#SideHustle, #Solopreneur, #WorkFromHome)
- No generic hashtags like #love, #instagood
- Start each hashtag with #, separate with spaces

Return ONLY the hashtags, one space between each, nothing else."""

CONTENT_IDEAS_PROMPT = """Generate {count} high-performing Instagram post ideas for a small business AI automation brand.

{brand_context}

Focus areas (if specified): {focus_areas}

For each idea, provide:
1. A scroll-stopping hook/title (10 words max) — make it feel urgent or personal
2. Brief description of the post content and angle (2-3 sentences)
3. Suggested media type (image, carousel, video/reel)
4. Core emotion we're targeting (fear of missing out, relief, inspiration, curiosity)

Format each idea as:
---
Title: [hook title]
Description: [description]
Media Type: [type]
Key Message: [one-sentence takeaway]
---

Prioritize: specific, relatable scenarios over generic tips. Name real pain points."""

IMPROVE_CAPTION_PROMPT = """Improve the following Instagram caption for a small business AI automation brand.

{brand_context}

Original caption:
{original_caption}

Improvement focus: {improvement_focus}

Requirements:
- Punch up the opening hook — it must stop the scroll
- Keep the core message but use plain, everyday language
- Make the caption feel relatable to the specific business role in context
- Trim any fluff — every sentence must earn its place
- Do not mention "free 30-minute discovery call" or similar discovery-call offers
- Strong CTA at the end
- Target 25-45 words
- Hard maximum 60 words
- Match the brand voice: confident, empathetic, results-focused
- Do NOT include hashtags

Return ONLY the improved caption, nothing else."""

STORY_CONTENT_PROMPT = """You are creating a daily Instagram Story for Polaris Innovations — an AI automation brand for small business owners.

{brand_context}

Story type: {story_type}
Today's topic area (if relevant): {topic}

Generate story content for the type above. Follow the exact format below — no extra text, no labels beyond what is shown.

{type_instructions}

Return ONLY the three fields in this exact format:
HEADLINE: [text]
BODY: [text]
IMAGE_TOPIC: [text]"""

_STORY_IMAGE_INSTRUCTIONS = """IMAGE_TOPIC: Abstract graphic design scene — NO people, NO faces, NO photography.
Dark navy background (#0A1428). Clean node-and-connection diagram, system architecture visualization, or data flow map relevant to the headline topic.
Use: glowing nodes, flowing lines, broken connections, pulsing orange failure points, electric blue data paths.
Aesthetic: modern SaaS / technical diagram — Stripe or Linear visual language. High contrast, flat, no gradients on shapes.
No robots, no holograms, no abstract art. Pure systems diagram."""

STORY_TYPE_INSTRUCTIONS = {
    "tip": """Create an operational insight story for mid-market founders and ops leaders.
HEADLINE: A sharp, specific label — e.g. "The integration layer is where AI dies" or "Ops insight:" — max 7 words
BODY: One specific, hard-won operational insight about AI implementation, systems design, or scaling — something a COO would forward to their team. 1-2 sentences, no fluff.
""" + _STORY_IMAGE_INSTRUCTIONS,

    "fact": """Create a "Did You Know?" story with a sharp stat or fact relevant to mid-market AI operations.
HEADLINE: "Did You Know?" or a pointed variant — max 5 words
BODY: One specific, striking fact about AI implementation failure rates, mid-market operational costs, or systems debt — include a number if possible. 1-2 sentences.
""" + _STORY_IMAGE_INSTRUCTIONS,

    "poll": """Create an engagement poll story for operators and founders. Format as a question image that invites DM replies.
HEADLINE: A direct operational question, max 8 words — something a COO or ops director has a strong opinion on
BODY: The question with 2 answer choices on separate lines — e.g. "A: We have documented failure paths\\nB: We're one outage away from chaos" — blunt and real
""" + _STORY_IMAGE_INSTRUCTIONS,

    "quote": """Create an original POV statement in the Polaris brand voice — for founders and operators of scaling companies.
HEADLINE: The statement itself — sharp, specific, max 12 words. Written as a hard-won operational truth, not motivation. NOT from a famous person.
BODY: One sentence that sharpens the point or invites operators to reflect — e.g. "DM me if your company is at this stage."
""" + _STORY_IMAGE_INSTRUCTIONS,
}

TRENDING_AUDIO_PROMPT = """You are a social media strategist specializing in Instagram Reels for business and entrepreneur content.

{brand_context}

The user is creating a Reel about: {topic}
Content type: {content_type}

Recommend 5 specific Instagram audio tracks that consistently perform well in the business / entrepreneur / self-improvement niche. Focus on tracks that have proven staying power — used heavily in motivational, business, and productivity Reels.

For each track provide:
- Exact track name and artist (real tracks you know from your training data)
- Why it fits this specific content topic
- The vibe / niche it dominates
- Caption energy it pairs with (motivational, educational, urgency, curiosity, etc.)

Prioritize:
- Instrumental or low-lyric tracks that don't compete with on-screen text
- Upbeat but professional — avoid party/club audio
- Tracks that have been used extensively in business/entrepreneur Reels
- Range from well-known to slightly under-the-radar

Format EXACTLY as:
---
Track: [name - artist]
Niche: [trending niche]
Vibe: [2-4 word energy description]
Why it fits: [1-2 sentences specific to this topic]
---

After the 5 tracks, add one line:
Top pick: [track name] - [one sentence reason]

Return only the formatted list, nothing else."""

ENGAGEMENT_RESPONSE_PROMPT = """Generate a genuine, on-brand reply to this Instagram comment for Polaris Innovations.

{brand_context}

Comment: {comment}
Context about the post: {post_context}

Requirements:
- Sound human and warm, not like a brand account
- If they asked a question, answer it directly and briefly
- Invite them to DM if the topic needs more depth
- Under 40 words
- No corporate language, no "Great question!"

Return ONLY the response text, nothing else."""
