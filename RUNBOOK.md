# Polaris CAKE Concierge Test Runbook

Purpose
- Validate the full comment-to-DM concierge pipeline before go-live.
- Confirm that a comment containing CAKE starts a DM flow that sells AI agent services.

Scope
- Instagram comment trigger
- Initial private DM send
- AI follow-up replies
- Lead qualification updates
- Duplicate-protection behavior

Prerequisites
- Connected Instagram account is active.
- App permissions include instagram_manage_comments and instagram_manage_messages.
- Target post exists and is visible.
- Trigger is configured for keyword CAKE.

Quick Commands
- Create or verify trigger:
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads setup
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads triggers
- Run one poll pass:
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads poll
- List leads:
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads list --limit 20
- Show one lead:
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads show LEAD_ID

10-Minute Pass/Fail Checklist

Test 1: Comment Trigger
1. From a non-owner test account, comment CAKE on the target post.
2. Run one poll pass.
3. Verify one new lead appears with status CONTACTED.
4. Verify first DM was sent.
Pass if
- Exactly one new lead is created and one initial DM is sent.
Fail if
- No lead, no DM, or duplicate leads for the same comment.

Test 2: Concierge Reply Quality
1. In DM, send: What does this cost?
2. Run one poll pass.
3. Verify reply is plain language and focused on AI agent services.
4. Verify no discovery-call wording appears.
Pass if
- Response is relevant, clear, and service-aligned.
Fail if
- Response is off-topic, overly technical, or contains discovery-call offers.

Test 3: Qualification Logic
1. In DM, send: Can we book this week?
2. Run one poll pass.
3. Verify lead status updates to QUALIFIED.
Pass if
- Lead status is QUALIFIED.
Fail if
- Status remains CONTACTED or REPLIED.

Test 4: Idempotency
1. Run poll two more times with no new comments/messages.
2. Verify no duplicate leads and no repeated assistant messages.
Pass if
- Counts and conversation remain unchanged.
Fail if
- New duplicates appear.

Test 5: Conversation Integrity
1. Open lead details for the same lead ID.
2. Verify ordered history includes initial DM, user messages, and assistant replies.
Pass if
- Thread is complete and readable for handoff.
Fail if
- Messages are missing or out of order.

Go/No-Go Rule
- Go live only when all 5 tests pass.
- If any fail, fix and rerun all tests.

Recommended Production Schedule
- Run polling every 2 minutes using Task Scheduler:
  - C:/Users/oates/AppData/Local/Programs/Python/Python313/python.exe -m polaris leads poll

Troubleshooting
- No new leads created:
  - Confirm trigger post ID and keyword match.
  - Confirm comment is on the watched post.
  - Confirm account/token is active.
- DM not sent:
  - Recheck instagram_manage_messages permission.
  - Check logs at logs/leads.log.
- Status not becoming QUALIFIED:
  - Ensure user message includes pricing/booking/availability intent terms.
- Duplicate leads:
  - Verify same comment ID is not being replayed from API edge cases.

Change Log
- Initial runbook created for CAKE concierge campaign testing.
