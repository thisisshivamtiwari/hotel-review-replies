# STUDY: hotel-review-replies

Notes for explaining this project in an interview: the problem, the design choices and why, what the numbers say,
where it fails, and likely questions with answers. All numbers come from [results/summary.json](results/summary.json).

## 1. The problem in one paragraph

Hotels reply to reviews in public, and AI tools now draft those replies with access to the booking system. The two
expensive mistakes are a **privacy leak** (the reply repeats the room number, a refund, a pregnancy or a proposal
the guest never wrote about) and an **invented fix** (the reply says a problem is solved, or promises a change,
when nothing has been done). The first is personal data published on the open web; the second is a public promise
the hotel can't keep. The question: is a "don't do that" rule in the prompt enough, or do you need to engineer
around it?

## 2. Design choices

| Choice | Why | Alternative considered |
|---|---|---|
| Made-up hotels, reviews and private notes | Leaks can only be scored if we know exactly what is private; real guest data is off limits | Public review datasets (no private notes to leak, so they can't test the main risk) |
| Same rules prompt in the three rules setups, plus a format-only "no rules" baseline | The rules setups differ only in context and post-processing; the baseline shows what the rules themselves are worth | Only rules setups (the first pass did this; with the rules almost nothing leaked, which hid the baseline risk) |
| Minimised context = one line ("stay found") | Data minimisation: the model can't leak what it never sees. The only private fact a reply needs is whether the guest really stayed | Redacting the notes (still sends structure and can miss things) |
| Deterministic checks that never see the private notes or the scoring terms | Otherwise the checker would be marked against its own answer key; it sees only what the reply may use | Scanning the reply for the guest's private terms (realistic, but it would score itself) |
| Up to 2 repairs, then flag for a person | Same loop as hotel-content-pipeline; a reply that still fails goes to a human, not to Google | Unlimited repairs (cost, and the model can loop) |
| Judge sees all eight replies to a review, shuffled | Blind to setup and model, and consistent across them; one call per review instead of eight | One call per reply (8x the cost, less consistent) |
| Leak terms written by hand, plus the judge, plus a flag review | Terms catch exact repeats cheaply, the judge catches paraphrase, the review removes false positives | Judge only (the AI Lab run showed the judge alone is not reliable enough) |
| Wilson intervals on the clean rate | 32 replies per cell is small; the interval shows what the data can and can't separate | Bootstrap (same answer for a single proportion, more code) |
| Record/replay cassettes and a CI gate | CI reruns the whole evaluation for free and fails if results drift or a setup gets worse than its baseline | Live calls in CI (cost, keys, flaky) |
| `--effort low` for Sonnet only | Haiku 4.5 doesn't support effort and the CLI ignores the flag for it silently (anthropics/claude-code#96386) | Passing it to both (looks controlled, isn't) |

## 3. Results

From [results/summary.json](results/summary.json), 32 made-up reviews, one reply per setup and model:

| | Haiku 4.5 unsafe | Haiku 4.5 clean | Sonnet 5.5 unsafe | Sonnet 5.5 clean |
|---|---|---|---|---|
| full notes, no rules | 12 | 20/32 | 3 | 28/32 |
| full notes + rules | 1 | 31/32 | 0 | 13/32 |
| minimised + rules | 1 | 31/32 | 0 | 18/32 |
| minimised + rules + checks + repair | 1 | 31/32 | 0 | 29/32 |

- Rules in the prompt: unsafe replies 15/64 -> 1/64 (p = 0.0002). Leaks 5/64 -> 0/64 (p = 0.058, not significant alone).
- Minimised context: 0 leaks in 128 replies, by construction, with no loss in safety.
- Sonnet's low "clean" with rules is operator notes ("verify before posting"), from the account-level instructions on
  the Claude Code account used. Checks + repair: 18/32 -> 29/32 clean (p = 0.004); 1 note the check missed was posted.
- Cost: Sonnet 5.5 at low effort $0.007 and 4 s a reply, $0.011 and 6 s with checks + repair; Haiku 4.5 $0.013 and
  20 s (default extended thinking, effort not supported).

The recommendation from this test: minimise the context (the model only needs to know whether the stay is real),
keep the rules in the prompt, run deterministic checks with a bounded repair loop, flag what still fails, and add a
check for invented reasons before trusting a small model unattended.

## 4. Failure modes

1. **Invented reasons.** "Following guest feedback, we've installed new pillows": the change is real, the cause is
   made up. Keyword checks can't see it. Haiku produced one in every rules setup.
2. **Operator notes in the output.** Instructions from outside the prompt (here, account-level ones) made Sonnet add
   "please verify before posting" lines. The regex caught 13 of 14 in the minimised setup; one phrased as
   "should be verified against hotel records before any further action is taken" slipped through.
3. **Leaks look like helpfulness.** Without rules, the leaks were attempts to be useful: "we refunded the difference
   at checkout", "we offered you a complimentary date change", "the non-refundable rate you booked". A reviewer
   reading them would see a defensive hotel publishing private dealings.
4. **Promises disguised as plans.** "We have arranged for a plumber to investigate and resolve the issue" when the
   cause is unknown and only a visit is booked.
5. **Suspicion leaks into tone.** "We always welcome feedback from genuine guests" to a reviewer with no booking.
6. **The judge is too strict on causal and mood wording.** 23 of 74 flags were overruled, mostly advice ("ask for a
   rear room"), restated policies and generic purposes ("to better serve our guests").
7. **Checks over-flag in edge cases**: a sensitive word list can hit innocent uses, and a number check flags any
   number the fact sheet doesn't contain.
8. **A failed lookup read as "not found" (fixed 24 Nov).** The first version showed the model "no stay matching this
   reviewer was found" whenever the lookup didn't say yes, including when it never answered, so the model would
   publicly tell a real guest their stay doesn't exist. Now there are three states (found, not found, not known),
   and a check holds any "we can't find your stay" the booking system didn't back. Before the fix, 8 of the 15 fault
   fixtures (a missing fact-sheet field, a timed-out model call) raised an exception that would stop the whole batch;
   now each is flagged for a person with the reason ([results/faults.json](results/faults.json)).

## 5. Ten interview questions

1. **Why made-up data?** To score a leak you need to know exactly what was private. Real booking notes are personal
   data I'd never use, and public reviews have no private notes, so they can't test the main risk.
2. **What is data minimisation here, and why does it beat a prompt rule?** The model gets only what the task needs:
   the review, the public fact sheet and whether the stay is real. A rule asks the model not to leak; minimisation
   makes leaking impossible. In this test the rule alone also reached 0 leaks, so the honest claim is
   defence in depth, not a measured improvement.
3. **Why don't the checks see the private notes?** If the checker scanned for the scoring terms it would be graded
   against its own answer key. It sees only what the reply may use, which also matches a real system where the
   checker shouldn't need extra access to personal data.
4. **How did you know the judge was right?** I didn't assume it. Every judge flag and leak-term hit was reviewed by
   hand against the data, with written rules (23 overruled, 1 retyped). I also searched every reply for operator
   notes and found one the check missed. Unflagged replies were not all read, which is a stated limitation.
5. **Why blind the judge?** It sees all eight replies to a review under shuffled letters, so it can't favour a setup or
   its own model family, and it applies one standard to all of them in one pass.
6. **Why Fisher's exact test and Wilson intervals?** Small counts (out of 32 or 64) and rates near 0 or 100%. Normal
   approximations break there.
7. **What surprised you?** The biggest blocker to posting unedited wasn't privacy; it was an instruction from outside
   my prompt making the model add notes for the operator, and my privacy rules made it more likely (2/32 -> 19/32).
   In production you have to test the whole stack the model runs in, not only your prompt.
8. **Why is Haiku dearer than Sonnet here?** In the Claude Code CLI Haiku 4.5 uses extended thinking by default and
   doesn't support the effort setting, so it wrote about 2,500 output tokens per draft. Sonnet at low effort wrote a
   few hundred. Price per token isn't price per task.
9. **How does CI work without an API key?** Every model call is recorded in cassettes keyed by a hash of model,
   prompts and effort. CI replays them, checks the replay reproduces summary.json exactly, and applies gate rules:
   no setup may leak more than its baseline, checks may not make things worse, and the recommended setup may post
   at most the one known problem.
10. **What would you do before using this for a real hotel?** Run it through the API without account-level
    instructions, three samples per cell, a second judge from another model family, a check for invented reasons,
    a person on every complaint reply at first, and a data-protection review of what the drafting tool can access.
