# Inbound DM Trigger System

## Overview

The **inbound DM trigger system** is an alternative to comment-based triggers that **doesn't require outbound messaging permissions** from Meta. It works by:

1. Monitoring your Instagram DMs for messages containing a trigger keyword (e.g., "CAKE")
2. Automatically responding with a personalized initial message
3. Continuing the conversation with AI-powered follow-ups

## Why Use Inbound DM Triggers?

Meta's API has strict restrictions on outbound messaging:
- **Comment-based triggers** require `instagram_manage_messages` permission (often denied for new apps)
- **Inbound DM triggers** use only read permissions (usually approved by default)

By switching to inbound DM triggers, you bypass Meta's permission review process entirely.

## How It Works

### User Flow

```
User sends DM: "CAKE"
         ↓
Polaris detects keyword in inbound message
         ↓
Automated response sent: "Thanks for messaging us about CAKE..."
         ↓
Lead created and tracked in database
         ↓
AI follow-up replies engage in conversation
```

### Under the Hood

- **Trigger Detection**: `poll_inbound_dm_triggers()` fetches all conversations and searches for keyword matches
- **Deduplication**: Messages are deduplicated by `inbound_message_id` to prevent duplicate leads
- **Lead Creation**: Each inbound match creates a lead record with full conversation history
- **AI Follow-up**: Same as comment triggers — AI responds to user replies

## Setup

### 1. Create a Trigger

```bash
python -m polaris leads setup
```

When prompted:
- **Post ID**: Use "0" (placeholder — inbound triggers don't attach to posts)
- **Trigger keyword**: `CAKE` (or your custom keyword)
- **Initial DM message**: Your niche-specific message ending with a question
- **AI follow-up**: Enable for automatic replies

### 2. Test Locally

```bash
python -m polaris leads poll_inbound
```

This runs one pass of inbound DM polling. Send a test DM to your account with your trigger keyword and verify the response.

### 3. Deploy to GitHub Actions

The workflow already uses `poll_inbound`:

```yaml
- name: Poll for CAKE DMs and respond
  run: python -m polaris leads poll_inbound
```

It runs every 5 minutes (configurable via cron). No additional setup needed.

## CLI Commands

### List Triggers
```bash
python -m polaris leads triggers
```

Shows all configured triggers (works for both comment and inbound DM triggers).

### Poll Inbound DMs (One Pass)
```bash
python -m polaris leads poll_inbound
```

Manually trigger one polling cycle. Useful for testing.

### View Leads
```bash
python -m polaris leads list
```

Shows all leads created from inbound DMs (and comments if using comment triggers).

### Pause/Resume Trigger
```bash
python -m polaris leads pause <trigger_id>
python -m polaris leads resume <trigger_id>
```

Works for both trigger types.

## Example Workflow

### Setup for Wedding Cake Business

```bash
$ python -m polaris leads setup

Setting up comment trigger for @your_cake_business

Enter the Instagram media ID of the post to watch: 0
Trigger keyword (e.g. INFO): CAKE
Initial DM message to send when keyword is detected (make it niche-specific and end with one clear question): Thanks for reaching out about CAKE! 🎂 We specialize in custom wedding cakes. Quick question: are you looking for a cake for a specific date, or are you still in the planning phase?
Enable AI follow-up replies? [Y/n]: y

Trigger #1 created!
  Post:    0
  Keyword: CAKE
  AI follow-up: enabled
```

### User sends: "CAKE"

Polaris detects the keyword and sends:

> Thanks for reaching out about CAKE! 🎂 We specialize in custom wedding cakes. Quick question: are you looking for a cake for a specific date, or are you still in the planning phase?

### User replies: "We're getting married in September"

AI generates contextual response:

> That's wonderful! September is a beautiful time for a wedding. For a custom cake, we typically recommend booking 6-8 weeks before the event. Do you have a specific flavor or design in mind? 🎨

## Database Fields

### Lead Model Updates

- **`inbound_message_id`** (nullable): The Instagram message ID (for inbound DM triggers)
- **`comment_id`** (nullable): The Instagram comment ID (for comment-based triggers)
- **`post_instagram_media_id`**: "0" for inbound DM triggers (placeholder)

Both `comment_id` and `inbound_message_id` have unique constraints to prevent duplicates.

## Troubleshooting

### No new leads appearing

1. **Verify trigger is active**: `python -m polaris leads triggers`
2. **Check API token**: Ensure `META_APP_ID`, `META_APP_SECRET`, and `DATABASE_URL` are set
3. **Send test DM**: Message your account with the exact trigger keyword
4. **Check logs**: `tail -f logs/leads.log`
5. **Manual poll**: `python -m polaris leads poll_inbound`

### Leads created but no responses

1. Verify **AI follow-up is enabled** on the trigger: `python -m polaris leads triggers`
2. Check **Anthropic API key** is set: `echo $ANTHROPIC_API_KEY`
3. Review lead status: `python -m polaris leads list`

### Database migration failed

If you get schema errors, run:
```bash
alembic upgrade head
```

This applies the migration for `inbound_message_id` support.

## Comparison: Comment vs. Inbound DM Triggers

| Aspect | Comment Triggers | Inbound DM Triggers |
|--------|-----------------|-------------------|
| **How triggered** | User comments on post | User sends DM |
| **Required permissions** | `instagram_manage_messages`, `pages_read_engagement` | `instagram_manage_messages` (read only) |
| **Meta approval** | Often denied | Usually approved |
| **Messaging window** | Subject to 24-hour restriction | No restriction (user-initiated) |
| **Public visibility** | Comments visible on post | Private DM |
| **Best for** | Mass outreach, CTA campaigns | Personal engagement, niche offers |

## Next Steps

1. **Create your first inbound trigger**: `python -m polaris leads setup`
2. **Test locally**: `python -m polaris leads poll_inbound`
3. **Deploy**: GitHub Actions workflow auto-runs every 5 minutes
4. **Monitor**: Check `logs/leads.log` for activity
5. **Refine**: Adjust initial message based on conversation quality

---

**Questions?** Check the main [README.md](README.md) for general project info.
