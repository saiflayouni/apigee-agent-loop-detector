#!/usr/bin/env python3
"""
Apigee X Loop Detection — GDE Demo

  python demo.py            # full before → after (structural)
  python demo.py before     # runaway cost simulation
  python demo.py after      # structural hop-count protection
  python demo.py semantic   # Phase 3: Gemini Flash semantic detection
"""

import sys
import time
import json
import urllib.request
import urllib.error

PROXY_URL     = "http://localhost:8998/ai-agent"
COST_PER_CALL = 0.002   # USD per Gemini Flash agentic call
BEFORE_CALLS  = 50      # cap for "before" simulation (real runaway: 1000+)

R = "\033[31m"; G = "\033[32m"; Y = "\033[33m"
C = "\033[36m"; W = "\033[1m";  X = "\033[0m"

BANNER = f"""
{W}╔══════════════════════════════════════════════════════════╗
║    Apigee X — Agentic Loop Detection Demo                ║
║    Protecting Gemini agents from infinite loops          ║
╚══════════════════════════════════════════════════════════╝{X}
"""

# Semantically similar intents — the agent is stuck asking the same thing
SEMANTIC_INTENTS = [
    "find the best pizza restaurant near me",
    "what's a good pizza place around here?",
    "recommend a pizza restaurant nearby",
    "where can I get great pizza close to me?",
    "show me top-rated pizza spots in my area",
    "pizza restaurants near my location",
    "best pizza delivery near me",
]


def before():
    print(f"{W}━━━  BEFORE Apigee: Unprotected Runaway Agent  ━━━{X}")
    print(f"{Y}No loop guard. The agent keeps calling the LLM...{X}\n")
    total = 0.0
    for i in range(1, BEFORE_CALLS + 1):
        total += COST_PER_CALL
        pct    = i / BEFORE_CALLS
        bar    = int(pct * 30)
        filled = f"{R}{'█' * bar}{X}" + ("░" * (30 - bar))
        print(
            f"\r  call {i:>3}  [{filled}]  cost: {R}${total:>5.3f}{X}",
            end="", flush=True
        )
        time.sleep(0.07)

    projected_1k = 1000 * COST_PER_CALL
    print(f"\n\n{R}✗  {BEFORE_CALLS} calls made — still looping. ${total:.2f} burned.{X}")
    print(f"   Real runaway reaches 1,000 calls → {R}${projected_1k:.2f}+{X} before timeout.\n")


def after():
    print(f"{W}━━━  AFTER Apigee: Structural Loop Detection Active  ━━━{X}")
    print(f"{G}Same agent, now routed through the Apigee proxy...{X}\n")

    hop = 0
    call_num = 1

    while True:
        req = urllib.request.Request(PROXY_URL)
        if hop > 0:
            req.add_header("X-Agent-Loop-Count", str(hop))

        try:
            with urllib.request.urlopen(req, timeout=5):
                print(f"  call {call_num:>3}  hop {hop:>2}  →  {G}200 OK{X}")
                hop += 1
                call_num += 1
                time.sleep(0.18)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                _print_blocked(e, call_num, hop)
            else:
                print(f"  {R}HTTP {e.code}{X}: {e.reason}")
            return
        except Exception as ex:
            print(f"  {R}Error:{X} {ex}")
            print("  Is the emulator running? Try: bash deploy.sh")
            return


def semantic():
    print(f"{W}━━━  Phase 3: Gemini Flash Semantic Loop Detection  ━━━{X}")
    print(f"{C}Agent asks the same question in different words — Apigee catches it.{X}\n")

    history = []
    hop = 0

    for i, intent in enumerate(SEMANTIC_INTENTS):
        history.append(intent)
        history_str = "||".join(history[-5:])

        body = json.dumps({"intent": intent}).encode()
        req  = urllib.request.Request(PROXY_URL, data=body)
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Agent-Loop-Count", str(hop))
        req.add_header("X-Agent-History", history_str)

        label = f'"{intent[:45]}{"…" if len(intent)>45 else ""}"'

        try:
            with urllib.request.urlopen(req, timeout=10):
                print(f"  call {i+1:>2}  hop {hop:>2}  →  {G}200 OK{X}  {Y}{label}{X}")
                hop += 1
                time.sleep(0.3)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"  call {i+1:>2}  hop {hop:>2}  →  {R}429 BLOCKED ✓{X}  {Y}{label}{X}")
                _print_blocked(e, i + 1, hop)
            else:
                print(f"  {R}HTTP {e.code}{X}: {e.reason}")
            return
        except Exception as ex:
            print(f"  {R}Error:{X} {ex}")
            print("  Is the emulator running and GEMINI_API_KEY set? Try: bash deploy.sh")
            return

    print(f"\n{Y}All intents passed — try adding more repetitions or lower the confidence threshold.{X}\n")


def _print_blocked(e, call_num, hop):
    body = json.loads(e.read().decode())
    dtype = body.get("detection_type", "structural")

    print(f"\n{W}── Apigee 429 response ─────────────────────────────────{X}")
    print(f"  detection_type  : {C}{dtype}{X}")
    print(f"  message         : {body.get('message')}")
    print(f"  hop_count       : {W}{body.get('hop_count')}{X}")

    if dtype == "semantic":
        print(f"  confidence      : {C}{body.get('semantic_confidence')}{X}")
        print(f"  reason          : {Y}{body.get('reason')}{X}")

    print(f"  calls_prevented : {W}{body.get('calls_prevented')}{X}")
    print(f"  cost_saved_usd  : {G}${body.get('cost_saved_usd')}{X}")
    print(f"{W}────────────────────────────────────────────────────────{X}\n")
    print(
        f"{G}✓  Loop killed at call #{call_num}. "
        f"{body.get('calls_prevented')} calls prevented. "
        f"${body.get('cost_saved_usd')} saved.{X}\n"
    )


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    print(BANNER)

    if mode in ("before", "both"):
        before()

    if mode == "both":
        print(f"  Press {W}Enter{X} to see the same agent protected by Apigee...", end="")
        input()
        print()

    if mode in ("after", "both"):
        after()

    if mode == "semantic":
        semantic()
