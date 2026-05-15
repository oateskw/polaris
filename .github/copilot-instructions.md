# Copilot Instructions for Polaris

## Project Purpose
- This project has two main functions: Instagram content generation and Instagram lead generation plus comment response.
- Treat those as separate workflows unless a task explicitly asks to connect them.
- Content generation creates captions, hashtags, carousels, stories, and reels.
- Lead generation handles comment-trigger DM outreach, inbound DM intake, and AI follow-up replies.

## Instagram Rules
- This repo automates Instagram lead capture, DM follow-up, and limited comment handling.
- Treat the lead pipeline as the source of truth for Instagram outreach.
- Keep public comment replies separate from lead creation and DM follow-up.
- Keep trigger-based comment handling, inbound DM handling, and follow-up handling in their own flows.

## Comment And DM Behavior
- If a comment matches an active trigger keyword, do not also generate or post a public reply.
- `CommentReplyService` is for public comments only and must stay isolated from lead creation logic.
- `LeadService.poll_triggers()` should send the initial outreach for comment-trigger leads.
- `LeadService.poll_inbound_dm_triggers()` should handle user-initiated inbound DMs.
- Prefer a direct DM first; use private-reply fallback only when the DM send is blocked.

## Meta Review Positioning
- The lead-generation feature is comment-to-DM, not direct-DM.
- Do not describe the user journey as "people DM me first"; the required action is a comment on one of my posts.
- If this feature is resubmitted to Meta, justify the four review permissions in terms of the comment-to-DM flow:
	- `pages_show_list`: find the connected Facebook Page and obtain the Page access token used by the app.
	- `pages_manage_metadata`: resolve the Page's linked Instagram business account so the app knows which IG account to monitor.
	- `instagram_manage_comments`: read comments on owned posts so keyword comments can trigger the lead workflow.
	- `instagram_manage_messages`: send the initial private reply/DM and continue the follow-up conversation.
- Keep the review narrative focused on public comments on owned posts being converted into private DM conversations.
- Do not frame the feature as a generic inbound DM system unless the task explicitly says to work on inbound DM triggers.

## Idempotency Rules
- Deduplicate comment leads by `comment_id` before creating a new lead.
- Deduplicate inbound DM leads by `inbound_message_id` before creating a new lead.
- Do not restart outreach when an open lead already exists for the same user and trigger.
- Do not create duplicate assistant messages when no new user message exists.

## Reply Rules
- Keep `PUBLIC_REPLIES_ENABLED` off unless a task explicitly asks to change public auto-replies.
- If a comment is trigger-matching, DM automation owns it and public reply automation must skip it.
- Keep reply copy short, human, and consistent with the Instagram voice already in the service prompt.

## Content Generation Rules
- Write content in plain language that a busy non-technical business owner understands on first read.
- Use the Polaris brand voice: plain, direct, confident, human, and free of fluff or jargon.
- Focus on practical outcomes, real examples, and simple breakdowns of what broke and what fixed it.
- Do not use consultant buzzwords like lead generation, pipeline optimization, or operational infrastructure in captions.
- Do not mention discovery-call offers such as a free 30-minute call.
- Captions should stay concise: target 25-45 words and never exceed 60 words.
- Keep each sentence short and direct.
- End captions with a simple CTA, usually DM or save.
- Do not add emojis in captions.
- Add hashtags separately and keep them relevant to operational excellence, systems thinking, B2B AI, and scaling companies.
- For hashtags, avoid solopreneur and generic engagement tags.
- For carousel content, prefer punchy hooks, short bullet points, and a clear problem-to-solution structure.
- For stories, keep the format strict and the copy sharp, specific, and opinionated.
- For reels, keep the content aligned with the brand voice and the selected audio track, and keep the visuals professional and practical.

## Safety And Config
- Do not edit `.env.example` in this repository.
- If a runtime setting needs to change, update `.env` instead.

## When Making Changes
- Preserve existing Instagram idempotency and separation-of-concerns behavior unless the task explicitly requires a change.
- Prefer the smallest targeted fix that keeps public-reply and DM automation boundaries intact.
- When touching Instagram automation, validate the exact path you changed with the narrowest relevant test or runbook step.