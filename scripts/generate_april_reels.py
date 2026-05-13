"""
Generate and schedule 14 Instagram reels for April 9 – May 9, 2026.
Run from project root: python scripts/generate_april_reels.py
"""

import subprocess
import re
import sys
import time

REEL_MESSAGING_BRIEF = (
    "Messaging standards: use plain language that anyone can understand on first read. "
    "Keep each reel focused on one clear point. Keep lines short and direct. "
    "Avoid jargon, technical terms, and stacked concepts. "
    "Use practical before/after outcomes and simple next steps."
)


REEL_VISUAL_BRIEF = (
    "Visual standards: photorealistic cinematic editorial imagery in real business environments. "
    "Use bright, cheerful daylight lighting, warm highlights, realistic screens, desks, phones, notebooks, and ops workspaces. "
    "Composition must feel like premium ad creative: one clear focal point, strong negative space, minimal clutter, and one message per frame. "
    "Style target: clean UI card overlays on top of a high-quality blurred background scene. "
    "Keep exposure balanced and uplifting. Avoid dark, heavy, or gloomy scenes. "
    "No cartoons, no clip art, no abstract system diagrams, no robots, no sci-fi, no text burned into generated image, no logos, no watermarks."
)

REELS = [
    {
        "topic": "We are mid-build on a 4-layer AI operational infrastructure. Here is the architecture.",
        "context": (
            "We just secured a new contract. We are currently building a complete AI operational "
            "infrastructure with four layers: a Unified Logic Parser for lead intake, an Autonomous "
            "Liaison Agent (Walled Garden) that handles lead communication before any human contact, "
            "a Mission Control custom Teams CRM architecture, and an Immutable Activity Log. "
            "Frame this as a real system in production. No client details. Target audience: COOs, "
            "ops directors, scaling founders at $2M-$10M companies. Abstract system diagram visual."
        ),
        "time": "2026-04-09 10:00",
    },
    {
        "topic": "Why most lead intake is architecturally broken — and what a Unified Logic Parser actually does.",
        "context": (
            "We are building a Unified Logic Parser for a client. It ingests leads from multiple "
            "channels, normalizes the data, and routes based on business logic rules. Most $2M-$10M "
            "companies have fragmented lead intake — leads come in from web forms, phone, email, social "
            "DMs, and nothing connects. This is the infrastructure fix. Specific, technical, authoritative. "
            "Abstract data flow diagram visual."
        ),
        "time": "2026-04-11 09:30",
    },
    {
        "topic": "The Walled Garden: why we built an Autonomous Liaison Agent before any human ever touches a lead.",
        "context": (
            "We are building an Autonomous Liaison Agent — a walled garden layer that handles all initial "
            "lead communication. The agent qualifies, responds, and routes before any human contact. "
            "This keeps leads warm, data clean, and the process consistent regardless of who is on the "
            "team that day. Frame as architecture decision, not a chatbot. Why this layer exists and what "
            "breaks without it. Abstract agent/flow diagram visual."
        ),
        "time": "2026-04-14 10:30",
    },
    {
        "topic": "Why we stopped recommending off-the-shelf CRMs and built Mission Control — a custom Teams architecture.",
        "context": (
            "We are building a custom CRM environment inside Microsoft Teams for a client — we call it "
            "Mission Control. Off-the-shelf CRMs force companies to adapt their operations to the tool. "
            "Mission Control is built around how this company actually operates. It is not a Salesforce "
            "replacement — it is operational command infrastructure. Frame this as an architecture philosophy "
            "decision with real consequences. Abstract command/control diagram visual."
        ),
        "time": "2026-04-16 09:00",
    },
    {
        "topic": "Accountability infrastructure: the Immutable Activity Log and why it becomes a competitive moat.",
        "context": (
            "We are building an Immutable Activity Log for a client — a tamper-proof audit trail of every "
            "action taken by AI agents and humans in the system. When something goes wrong you know exactly "
            "what happened, when, and who or what did it. At scale, this is compliance, legal protection, "
            "and operational trust. Most companies have no audit trail. This is the layer that makes AI "
            "deployment defensible. Abstract ledger/log diagram visual."
        ),
        "time": "2026-04-18 10:00",
    },
    {
        "topic": "How the 4 layers of an AI operational stack connect — the integration story.",
        "context": (
            "The 4 layers in sequence: Unified Logic Parser feeds into the Autonomous Liaison Agent, "
            "which feeds into Mission Control CRM, which is recorded in the Immutable Activity Log. "
            "Each layer depends on the previous. Most AI implementations fail at the integration layer — "
            "individual tools that don't talk to each other. Show the data flow and why the architecture "
            "is designed this way. Abstract system integration diagram."
        ),
        "time": "2026-04-21 09:30",
    },
    {
        "topic": "What a $5M company's operations look like before and after AI infrastructure is in place.",
        "context": (
            "Before: leads from 4 different channels with no unified intake, manual routing, a CRM nobody "
            "updates, dropped balls with no accountability. After: unified logic parser, autonomous first "
            "response, mission control visibility, full immutable audit trail. No client details — this is "
            "the operational pattern we see across mid-market companies. Concrete, specific, no buzzwords. "
            "Before/after comparison diagram visual."
        ),
        "time": "2026-04-23 10:00",
    },
    {
        "topic": "Second build in progress: Intelligent Voice Gateway, Proprietary CRM, Automated Outbound Intelligence — one revenue engine.",
        "context": (
            "We secured a second contract. This client has a different operational profile — voice is the "
            "primary lead channel, they need proprietary CRM logic, and outbound follow-up is broken. "
            "Three layers: Intelligent Voice Gateway, Proprietary CRM and Lead Logic, Automated Outbound "
            "and Follow-Up Intelligence. Frame as currently in production, no client details. Abstract "
            "system overview diagram."
        ),
        "time": "2026-04-25 09:00",
    },
    {
        "topic": "When voice is your primary lead channel: what the Intelligent Voice Gateway actually does.",
        "context": (
            "We are building an Intelligent Voice Gateway for a client. AI handles inbound voice leads — "
            "qualifies them, captures structured data, routes them, and logs everything. When your business "
            "runs on phone calls you cannot afford to miss one or handle it inconsistently. This is the "
            "infrastructure layer that makes voice leads as trackable and reliable as form submissions. "
            "Abstract voice/routing flow diagram."
        ),
        "time": "2026-04-28 10:30",
    },
    {
        "topic": "Why we are building a proprietary CRM instead of customizing an existing one.",
        "context": (
            "For this client, off-the-shelf CRMs — even heavily customized — could not support their lead "
            "logic. We are building a proprietary CRM with their exact lead routing, scoring, and workflow "
            "logic baked in from the start. Ownership of your data model is a strategic asset at this scale. "
            "Frame as a deliberate architecture decision, not a vendor complaint. Abstract data model/logic "
            "diagram visual."
        ),
        "time": "2026-04-30 09:00",
    },
    {
        "topic": "The math on follow-up timing — and why we built Automated Outbound and Follow-Up Intelligence.",
        "context": (
            "Building Automated Outbound and Follow-Up Intelligence for a client. Most businesses follow "
            "up once or twice. Studies show 80 percent of sales happen after the 5th contact. This system "
            "tracks lead state and triggers the right outbound message at the right time automatically — "
            "no manual chasing. The math is brutal for companies that don't have this. Specific data angle, "
            "authoritative. Abstract outbound sequence/timing diagram visual."
        ),
        "time": "2026-05-02 10:00",
    },
    {
        "topic": "How the Voice Gateway, Proprietary CRM, and Outbound Intelligence work as one connected revenue engine.",
        "context": (
            "The 3 layers in sequence: Intelligent Voice Gateway captures and qualifies the lead, Proprietary "
            "CRM tracks lead state and logic, Automated Outbound Intelligence closes the loop. Show the data "
            "flow between layers. Each layer is only as effective as the one before it. The integration story "
            "is where the value actually lives. Abstract 3-layer system integration diagram."
        ),
        "time": "2026-05-05 09:30",
    },
    {
        "topic": "The architecture pattern we keep deploying across clients — two different industries, same infrastructure logic.",
        "context": (
            "Two client builds: one with a 4-layer intake and control stack, one with a 3-layer voice and "
            "outbound revenue engine. Different industries, different tools, but the same underlying pattern: "
            "unified intake, autonomous handling, operational visibility, accountability layer. This is the "
            "AI operational infrastructure pattern for companies at $2M-$10M. Not a product. A methodology. "
            "Abstract pattern/architecture comparison diagram."
        ),
        "time": "2026-05-07 10:00",
    },
    {
        "topic": "What it takes to build operational AI infrastructure — and the type of company it is built for.",
        "context": (
            "Polaris Innovations builds AI operational infrastructure for $2M-$10M companies. Not chatbots. "
            "Not automations. Architecture. We are mid-build on two contracts right now. Projects run "
            "$10k-$50k with multi-year retainer options. The companies that need this are running on "
            "spreadsheets and institutional knowledge and they are one key departure from collapse. "
            "CTA: DM to start a discovery conversation. Direct, no fluff, no hype. "
            "Abstract infrastructure/architecture diagram visual."
        ),
        "time": "2026-05-09 09:00",
    },
]


def _enhanced_reel_context(reel: dict, index: int) -> str:
    """Apply a shared quality/messaging brief to each reel context.

    This keeps every reel aligned to the stronger Facebook creative standard
    without rewriting each reel entry by hand.
    """
    chapter = f"Reel chapter {index + 1} of {len(REELS)}"
    return "\n\n".join(
        [
            REEL_MESSAGING_BRIEF,
            REEL_VISUAL_BRIEF,
            chapter,
            reel["context"],
        ]
    )


def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"GENERATING: {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, capture_output=False, text=True)
    return result.returncode


def generate_and_schedule(reel, index):
    label = f"Reel {index+1}/14 — {reel['time']}"
    print(f"\n{'#'*60}")
    print(f"  {label}")
    print(f"  Topic: {reel['topic'][:80]}...")
    print(f"{'#'*60}")

    # Generate
    gen_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "polaris",
            "content",
            "generate",
            "--reel",
            "--topic",
            reel["topic"],
            "--context",
            _enhanced_reel_context(reel, index),
            "--audio",
            "cinematic",
        ],
        capture_output=True,
        text=True,
    )

    print(gen_result.stdout)
    if gen_result.stderr:
        print("STDERR:", gen_result.stderr[-2000:])

    # Parse content ID
    match = re.search(r"Content saved with ID:\s*(\d+)", gen_result.stdout)
    if not match:
        print(
            f"ERROR: Could not parse content ID for reel {index+1}. Skipping schedule."
        )
        return None

    content_id = match.group(1)
    print(f"\nContent ID: {content_id} — scheduling for {reel['time']}")

    # Schedule
    sched_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "polaris",
            "schedule",
            "create",
            "--content-id",
            content_id,
            "--time",
            reel["time"],
        ],
        capture_output=True,
        text=True,
    )
    print(sched_result.stdout)
    if sched_result.stderr:
        print("STDERR:", sched_result.stderr[-500:])

    return content_id


if __name__ == "__main__":
    print("Polaris — April/May 2026 Reel Generation")
    print(f"Generating {len(REELS)} reels...\n")

    results = []
    for i, reel in enumerate(REELS):
        content_id = generate_and_schedule(reel, i)
        results.append({"index": i + 1, "time": reel["time"], "content_id": content_id})
        # Brief pause between generations
        if i < len(REELS) - 1:
            time.sleep(2)

    print("\n\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    for r in results:
        status = f"ID {r['content_id']}" if r["content_id"] else "FAILED"
        print(f"  Reel {r['index']:02d} | {r['time']} | {status}")
