# Fact cards: index

One short page per topic, each fact with its source. Read these instead of the whole spec and evidence.
2026-11-20.

## Cards

| Card | The question it answers |
|---|---|
| `state.md` | Where does the deep-sleep work stand, what is open, which commits hold the code? |
| `wake-path.md` | What must happen for a wake to reach Linux, and how far did each run get? |
| `boot-chain.md` | How does the M1 boot, which loader does it run, how is it restored? |
| `run-recipes.md` | Which commands, in which order, for each kind of run, and what each refuses? |
| `sleep-entry.md` | What does the entry do from `begin` to the commit, against macOS? |
| `candidates.md` | What is each candidate C1-C18, and what did switching it show? |
| `c3-words.md` | What are the three C3 words, their values, and the C3 record? |
| `records.md` | How are the power-chip bytes `0x9f04`-`0x9f0d` and the other records read? |
| `watchdogs.md` | Which watchdogs, who arms them when, and how a run ends without hands? |
| `pmp.md` | How is `pmp` started under Linux, and what does it exchange? |
| `coprocessors.md` | How is each coprocessor stopped before sleep and started after? |
| `power-domains.md` | Which power-domain words matter at the commit and at the wake? |
| `aurora-prior-art.md` | What do Aurora Silicon's repositories already have, and where? |

## How to use the cards

1. Read `state.md` first, then the card for your component.
2. Open the spec and the evidence only through a card's pointers (grep the section, read the range).
3. When you learn something, add one line to the card with its source in brackets.
4. Run `tools/prior-art.sh <component>` before any probe or build.
5. A fact without a source does not go on a card; say "not read" instead.
