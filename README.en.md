> 🌐 **Languages**: **[🇬🇧 English（当前）](#)** · [🇨🇳 中文](README.md)
>
> 👉 Chinese version is the original; this English version is a technical summary tailored for AI Engineer / AI Consultant interviewers — focusing on architecture, pipeline design, and quality gating mechanisms.

# 《天黑之前》(Before Nightfall) — AI-Assisted Long-Form Novel Writing Engine

> **TL;DR for technical readers**: A production-shaped LLM application that orchestrates multi-stage prompt generation, enforces a three-layer guardrail system, persists structured state across a 70-80 chapter novel arc, and degrades gracefully when API keys are absent. Built as a Human-in-the-Loop QA pipeline where an autonomous writing agent (Claude / Cline) generates prose, but a human author retains final approval before any chapter lands in `chapters/`.

---

## 🔀 Project Background & Credits

This project is built on and customizes the AI-assisted writing engine architecture from
[Open Souls](https://github.com/open-souls/open-souls), including its planner-writer-editor pipeline,
quality gate mechanisms, and character state tracking design. On top of this foundation, this project
configures its own worldview, character system, and plot outline, with writing standards and some
engineering details adapted for a crime/mystery genre.

---

## 💡 Technical Highlights (for AI Engineering audiences)

This project demonstrates the following LLM application engineering capabilities. All features are implemented in the `engine/` and `tools/` directories and are runnable today.

- **Prompt Engineering & Orchestration** — A multi-stage prompt orchestration pipeline: `engine/writer.py` implements `brief → compose → plan → draft` as four discrete stages, each emitting a standalone structured prompt file for downstream consumption.
- **Guardrail System** — A three-layer hard quality gate: `engine/prose_lint.py` (8 classes of AI-writing anti-patterns) + `engine/safety_lint.py` (content safety) + `tools/check_chapter_quality.ps1` (three-metric word count). Any failure → `BLOCKED`, no disk write permitted.
- **Human-in-the-Loop QA** — Two-layer review mechanism: Cline (AI agent) is the primary executor, but a human author retains final approval. See `.clinerules` §11.2 for the enforced workflow. Notably, **Claude's self-reported PASS does not grant write permission** — only local gate PASS does.
- **Graceful Degradation** — When `ANTHROPIC_API_KEY` is not configured, the system automatically downgrades to "Cline collaboration mode" (`run_dispatch.py` skips remote dispatch). The pipeline never blocks on missing credentials.
- **Structured State Management** — Long-horizon task persistence: `arc.json` (main plot beats + side-case progress) + `ties.json` (character relationship graph) + character tracking blocks in `CAST.md` + `tools/cast_absence_scan.py` for absence-threshold monitoring.
- **Incremental CI Gating** — PR-level incremental gate: `tools/validate_changed.py` by default only validates chapters modified in `git diff HEAD~1..HEAD`. When shared gate code is modified, the tool refuses and demands explicit `--full` flag — preventing accidental under-validation.

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│              《天黑之前》  Novel Writing Workflow                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────┐      ┌──────────────────┐      ┌─────────────────┐    │
│   │  Cline  │─────▶│  engine/writer.py │─────▶│  prompts/*.md   │    │
│   │ (human  │      │  brief/compose/  │      │  (planner +     │    │
│   │  review)│      │  plan/draft       │      │   writer prompt)│    │
│   └─────────┘      └──────────────────┘      └─────────────────┘    │
│        ▲                                              │              │
│        │              ┌──────────────────┐             ▼              │
│        └──────────────│  Claude API      │◀────┌─────────────────┐    │
│         reads PASS    │  (optional,      │     │ engine/run_     │    │
│         before write  │   enabled with   │     │ dispatch.py     │    │
│                       │   API key)       │     │                 │    │
│                       └──────────────────┘     └─────────────────┘    │
│                                                      │               │
│                                                      ▼               │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │
│   │ chapter_   │  │ prose_     │  │ safety_    │  │ batch_     │    │
│   │ stats.ps1  │  │ lint.py    │  │ lint.py    │  │ rewrite.py │    │
│   │ (3 word    │  │ (AI anti-  │  │ (content   │  │ (batch     │    │
│   │  counts)   │  │  patterns) │  │  safety)   │  │  rewrite)  │    │
│   └────────────┘  └────────────┘  └────────────┘  └────────────┘    │
│         ▼                ▼                ▼               ▼         │
│   ┌─────────────────────────────────────────────────────────────┐    │
│   │            chapters/Chapter_NN.md  (finalized chapters)        │    │
│   └─────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Key design decisions

- **Cline is the primary executor** — reads prompts, reads PASS reports, makes final commit decisions
- **`engine/writer.py` is the orchestrator** — emits prompt files; does not call the API directly (semi-automatic mode)
- **Claude API is optional** — enabled via `ANTHROPIC_API_KEY` + `run_dispatch.py` for remote dispatch
- **Lint is a hard gate** — `prose_lint.py` + `safety_lint.py` + `chapter_stats.ps1`; failure → `BLOCKED`
- **Human review is the final gate** — Cline reviews + author reviews; "leave the laptop on, leave VS Code open, let it run" model

---

## 🛠️ Toolchain Workflow (the core mechanism)

### Step-by-step: writing Chapter N

```
       ┌─────────────────────────────────────────┐
   ①   │  python engine/writer.py brief <N>      │  ← Brief (recent chapters + beats + cast + dark threads)
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ②   │  python engine/writer.py compose <N>    │  ← Generate planner + writer prompt files
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ③   │  python engine/run_dispatch.py \         │  ← Optional: dispatch to Claude API
       │     --chapters <N> --effort high         │     (skipped if no key → Cline mode)
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ④   │  prose_lint + safety_lint + word count  │  ← Three gates; failure → BLOCKED
       └─────────────────────────────────────────┘
                            ▼
       ┌─────────────────────────────────────────┐
   ⑤   │  Cline reads PASS report → writes to    │  ← Final human review before commit
       │     chapters/                            │
       └─────────────────────────────────────────┘
```

### Key engineering principles

| Principle | Implementation |
|---|---|
| **Cline as primary executor** | `writer.py` never calls the API directly; Cline reads prompts, writes, reviews |
| **Pluggable Claude API backend** | `ANTHROPIC_API_KEY` → `run_dispatch.py` dispatches remotely |
| **Resumable long-running pipeline** | Each step is an independent command; state files (`prompts/.results/Chapter_NN.md`) checkpointed to disk |
| **Human-in-the-loop final gate** | Cline writes → author reviews → edits → commits |
| **Full audit trail** | `arc.json` + `ties.json` + `CAST.md` auto-tracked blocks + `dossier.md` |

---

## 📁 Project Structure

```
Novel_New/                          ← repo root
├── README.md / README.en.md        ← Chinese / English README
├── .clinerules                     ← writing spec (v3.1 · 2026/8/31)
├── .env.example                    ← environment variable template
├── .gitignore                      ← Git exclusion rules
│
├── CAST.md                         ← character registry
├── OUTLINE.md                      ← main outline + per-chapter status
├── CLUES.md / CLUES_TRACKER.md     ← mystery clue tracking
├── WORLDVIEW.md / PSYCHOLOGY.md    ← world-building & forensic psychology glossary
├── WORDCOUNT_RULE.md               ← three-metric word count spec
├── arc.json / ties.json            ← structured state persistence
│
├── chapters/                       ← finalized chapter prose (Chapter_01.md … Chapter_14.md)
│
├── engine/                         ← core orchestration (Python)
│   ├── writer.py                   ← brief / compose / plan / draft (the four prompt stages)
│   ├── run_dispatch.py             ← budget + timeout + side-effect-controlled Claude dispatch
│   ├── prose_lint.py               ← 8 anti-pattern detector (em-dash, template dialogue, …)
│   ├── safety_lint.py              ← content safety gate
│   ├── cast.py / soul.py / season.py / trace.py / validate.py
│   └── batch_rewrite.py / _extract_ships.py
│
├── tools/                          ← quality gate tooling
│   ├── validate_changed.py         ← incremental CI gate (only validates changed chapters)
│   ├── check_chapter_quality.ps1   ← word count three-metric
│   ├── chapter_stats.ps1           ← detailed per-chapter statistics
│   ├── prescreen.py                ← pre-push fast screen
│   ├── cast_absence_scan.py        ← character absence threshold monitor
│   ├── punct_scan.py               ← punctuation / formatting scanner
│   └── smoke_test.py
│
├── prompts/                        ← generated prompts + batch extract reports
│   ├── Chapter_NN_plan.md          ← planner prompt
│   ├── Chapter_NN_draft.md         ← writer prompt (with planner JSON)
│   ├── C1_priority_matrix.md       ← C1 priority matrix
│   └── extract_ships_Chapter_NN.md ← relationship-line extraction reports
│
└── .claude/skills/                 ← Claude skill definitions (editorial workflow)
    ├── bianjibu/                   ← editorial department skill (6 sub-agents)
    └── wenbi-review/               ← prose review skill
```

---

## 🔧 Optional: API Key Configuration (for remote dispatch)

```bash
# 1. Copy env template
cp .env.example .env

# 2. Edit .env and fill in real key
# ANTHROPIC_API_KEY=sk-ant-...

# 3. Verify run_dispatch.py works
python engine/run_dispatch.py --chapters 14 --effort high --dry-run
```

**Without an API key, the toolchain automatically downgrades** to Cline collaboration mode — `run_dispatch.py` skips remote dispatch, and Cline reads the prompt files itself to write the prose. **The pipeline never blocks on missing credentials** (graceful degradation).

---

## 🎯 Current Progress

- ✅ **Chapters 01–14 finalized** (v3.1 standard: 1800–2200 chars/chapter; latest: Chapter 14 "老槐树" / Side-case 3 opening, completed 2026/9/3)
- 🟡 **Chapter 15 pending** — Side-case 3 mid-arc (Stakeout at 7:45 + profiling suspect)
- 🛠️ **AI auto-writing toolchain ready** (brief / compose / dispatch / lint, full pipeline validated)
- 📊 **Structured state persistence** (`arc.json` main beats + `ties.json` character graph)

---

## 🔒 Copyright & License

> **Copyright & Privacy Notice**: The novel prose content in this repository (`chapters/` directory, `CAST.md`, `OUTLINE.md`, and other creative-writing specification files) is for the author's own creative reference only. No external transmission, derivative works, commercial use, or republication is permitted without explicit permission. Copyright © 2026, all rights reserved by the original author.
>
> The engineering code and system architecture in this repository (`engine/`, `tools/` directories, and the pipeline design documented in this README) **may be freely viewed as a technical capability showcase**. Reuse is permitted with attribution to the source.

---

## 📜 Version

- **Writing spec version**: v3.1 (2026/8/31, three revisions)
- **Architecture version**: Dual-mode (Cline collaboration / Claude API dispatch)
- **Total chapter plan**: 70–80 chapters × ~2000 chars = 140k–176k chars total

