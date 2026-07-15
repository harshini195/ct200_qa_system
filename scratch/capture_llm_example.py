"""
Run this LOCALLY (on your Mac, inside the project venv, with a real
GROQ_API_KEY set) to capture a genuine example of the LLM call succeeding,
retrying, or failing -- for pasting into APPROACH.md as real evidence
instead of a hypothetical description.

Usage:
    cd ct200-qa-system
    source venv/bin/activate
    export GROQ_API_KEY=your_real_key_here
    python scratch/capture_llm_example.py

What it does:
  1. Pulls a genuinely gnarly section from the real manual (the error-code
     table + surrounding prose -- lots of structured data for the model to
     mangle).
  2. Calls your actual app.llm_client.generate_test_cases() -- the REAL
     code path your API uses, not a simplified copy.
  3. Runs it multiple times (LLMs are non-deterministic; one call might
     succeed cleanly while another mangles the JSON).
  4. Writes every attempt's raw response + parse result to
     scratch/llm_capture_output.md, ready to paste snippets from into
     APPROACH.md.

If none of the runs happen to fail, that's still useful and honest --
paste a real SUCCESS transcript into APPROACH.md instead of a hypothetical
one, and say so explicitly ("ran N live calls, M succeeded first try, ran
a follow-up strategy such as X to also exercise the failure path").
"""
import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import llm_client  # noqa: E402

# A genuinely tricky chunk: table + prose + cross-references, real text
# from data/ct200_manual.md section 4.2 + 4.3.
SOURCE_TEXT = """### 4.2 Error Codes

| Code | Meaning | Device Behavior |
|---|---|---|
| E1 | Cuff not connected or leak detected | Aborts measurement, displays E1 |
| E2 | Motion artifact detected during measurement | Aborts measurement, displays E2, prompts retry |
| E3 | Overpressure condition | Auto-deflates within 2 seconds, displays E3 |
| E4 | Low battery during measurement | Aborts measurement, displays E4 |
| E5 | Internal sensor fault | Device disables measurement function, displays E5 until serviced |

### 4.3 Alarm Thresholds

The device does not sound an audible alarm for elevated readings by default;
audible alarms are limited to the E1-E5 error conditions above and are
user-configurable in the settings menu, except for E3 (overpressure), which
cannot be silenced for safety reasons."""

N_RUNS = 5


def main():
    if not os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY not set -- this script needs a REAL key to be")
        print("worth anything (it would otherwise just hit mock mode).")
        print("export GROQ_API_KEY=... and re-run.")
        sys.exit(1)

    out_path = os.path.join(os.path.dirname(__file__), "llm_capture_output.md")
    lines = [
        f"# LLM capture run -- {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Model: {llm_client.GROQ_MODEL}",
        f"Runs: {N_RUNS}",
        "",
    ]

    messages = [
        {"role": "system", "content": llm_client.SYSTEM_PROMPT},
        {"role": "user", "content": f"Manual section text:\n\n{SOURCE_TEXT}"},
    ]

    for i in range(1, N_RUNS + 1):
        print(f"--- run {i}/{N_RUNS} ---")
        lines.append(f"## Run {i}")
        lines.append("")

        raw1 = llm_client._call_groq(messages)
        parsed1, err1 = llm_client._try_parse(raw1)
        lines.append(f"**First attempt: {'valid' if parsed1 else 'INVALID -- ' + str(err1)}**")
        lines.append("```")
        lines.append(raw1[:2500])
        lines.append("```")
        print(f"first attempt: {'valid' if parsed1 else 'invalid: ' + str(err1)}")

        if parsed1 is None:
            retry_messages = messages + [
                {"role": "assistant", "content": raw1},
                {"role": "user", "content": (
                    "Your last reply was not valid JSON matching the required shape "
                    f"(error: {err1}). Reply again with ONLY the JSON object, no "
                    "other text, no markdown fences."
                )},
            ]
            raw2 = llm_client._call_groq(retry_messages)
            parsed2, err2 = llm_client._try_parse(raw2)
            lines.append("")
            lines.append(f"**Retry attempt: {'valid' if parsed2 else 'INVALID -- ' + str(err2)}**")
            lines.append("```")
            lines.append(raw2[:2500])
            lines.append("```")
            print(f"retry attempt: {'valid' if parsed2 else 'invalid: ' + str(err2)}")

        lines.append("")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    print()
    print(f"Wrote {out_path}")
    print("Open it, find the most interesting run (ideally one where the")
    print("first attempt was invalid), and paste that transcript into")
    print("APPROACH.md under the LLM prompt design section as real evidence.")


if __name__ == "__main__":
    main()
