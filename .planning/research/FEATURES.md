# Feature Research

**Domain:** Personal music practice tracker + practice-routine builder (Music Lesson Tracker module for Sentinel of Mnemosyne)
**Researched:** 2026-07-08
**Confidence:** MEDIUM (PART A: cross-checked against 5-6 established practice-tracker apps and official ListenBrainz/Discogs docs; PART B: cross-checked across multiple independent pedagogy sources per instrument, consistent with well-known method-book conventions — no single-source claims)

> **Supersedes** the prior FEATURES.md content (arscontexta/second-brain feature research for the v0.4.1 "Restore the Second-Brain Core" milestone, formerly mislabeled v0.6.0). That milestone shipped 2026-07-07 and its research is archived in `.planning/milestones/v0.4.1-ROADMAP.md`. This file now covers the **new** v0.6.0 Music Lesson Tracker milestone.

---

## PART A — Practice Tracker Feature Landscape

### Table Stakes (Users Expect These)

Features every practice-journal / lesson-tracker product on the market has. Missing these makes the module feel like a toy, not a journal.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Practice session logging (duration, instrument, pieces/exercises worked, focus area, freeform notes) | Every reviewed app (Andante, Modacity, Instrumentive, Legato, Practis, Better Practice) treats this as the core primitive — it's the "journal" in practice journal | LOW | Maps directly to `/music/practice-log/[date].md` in the vault; a session is a single markdown note with `_schema` frontmatter (duration_min, instrument, pieces[], focus_area, mood/energy) |
| Mood / energy / focus self-rating per session | Andante and Instrumentive both log mood/focus as a lightweight 1-5 or emoji field; used to correlate practice quality with conditions over time | LOW | Simple frontmatter field; no UI beyond a prompt in the logging flow (chat or Discord command) |
| Per-piece / per-exercise time tracking | Instrumentive and Athenify explicitly split time by piece and by skill/technique, not just total session time — this is what makes "how long have I worked on X" answerable at all | MEDIUM | Requires the session log to model an array of `{item, minutes}` sub-entries, not just one duration field |
| Practice streaks | Andante, Legato, Athenify all gamify via streak counters — this is the single most common "hook" feature across every competitor | LOW | Pure derived/computed value from session log dates; no new storage, just a query over existing logs |
| Practice-history query / recall ("what did I work on last week?", "how long on this piece?") | This is the explicit differentiator of a *journal* vs. a bare timer — table stakes for anything calling itself a "tracker," and it's the killer feature this module gets almost for free by riding the existing Vault + Recall infrastructure | MEDIUM | This is where the module gets outsized leverage: it doesn't need bespoke NLQ — the same `Recall`/vault-search seam that already answers "what have we talked about" answers "what did I practice," provided sessions are well-tagged and named consistently (reuse VAULT/NOTE schema conventions from Phase 44/45) |
| Aggregate summaries (weekly/monthly time totals, per-instrument split) | Practis, tuneUPGRADE, Instrumentive all show 7-day/30-day/all-time rollups — users expect a "how am I doing overall" view, not just raw logs | MEDIUM | Computed report, not new storage; can be a scheduled digest (reuses existing 6 Rs pipeline cadence) or an on-demand query |
| Idea capture for chord progressions and melody fragments | Every gigging/writing musician needs a fast way to jot "I found this progression, don't lose it" — competitors (iReal Pro, voice-memo habits, notebook apps) all solve this in some form; a music module without it feels incomplete for a musician who produces | LOW–MEDIUM | See dedicated sub-section below — this is the one feature that needs real format design work, not just a markdown note |

### Differentiators (Competitive Advantage)

Features that set this module apart from commodity practice-tracker apps — mostly because it inherits infrastructure those apps don't have.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Practice-routine builder generating instrument-specific routines | No mainstream practice tracker *generates* a routine from pedagogy — they log time against a routine the user already knows. Combining PART B pedagogy with the user's own practice-history (what's been neglected, what's plateaued) into an auto-generated session plan is a genuinely differentiated feature no commodity app offers | HIGH | Needs: (1) a pedagogy knowledge base per instrument/domain (seed from PART B below), (2) a query into recent practice history to detect neglect/plateau, (3) a generation step (LLM prompt templated on the pedagogy KB + history). This is the most novel, most complex, and highest-value feature in the module |
| Conversational / chat-native logging and querying | Because this rides the Sentinel's existing chat + Discord interface, session logging and history queries happen in natural language ("logged 30 min on the F major scale, felt sluggish") instead of a bespoke UI form — competitor apps are all app-first, form-first | MEDIUM | Reuses existing message-processing pipeline; mostly a parsing/extraction problem (structured fields from freeform chat text) plus a vault-write step |
| Cross-domain recall tying practice to the rest of the second brain | Because everything lands in the same Vault, a practice session can be woven into the same graph as journal entries, other Session summaries, and Pathfinder module notes — "what was I stressed about the week my guitar practice dropped off" becomes answerable in a way no siloed practice app can do | MEDIUM | Leverages VAULT-02 PARA taxonomy and existing semantic recall (Phase 40) essentially for free — this is the single biggest reason to build this as a module rather than adopt an existing app |
| Structured, queryable chord-progression / melody-idea store | iReal Pro proves a compact text notation for chord progressions is viable and has 15+ years of validation; capturing progressions in a similar structured-but-plain-text form (not audio-only voice memos) makes them searchable/reusable across the vault (e.g. "find every idea in a minor key I haven't touched in 3 months") | MEDIUM | Format design: adopt an iReal-Pro-inspired plain-text chord grid (bar \| bar \| bar) stored as a fenced code block or dedicated frontmatter field in `/music/ideas/`, NOT the URL-encoded iReal format itself (that's a closed, app-specific encoding) — see Feature Dependencies below |
| Skill-category time balance view | Athenify's "time per technique" concept extended: because PART B pedagogy defines named skill categories per instrument (technique, repertoire, ear-training, theory, production-workflow), the module can show *actual* imbalance against the *prescribed* balance from the routine builder, not just an arbitrary self-defined tag | MEDIUM | Depends on the routine builder's skill taxonomy being the same taxonomy used for logging focus_area |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Built-in audio recording, pitch/timing analysis, or tuner/metronome tooling | Modacity and several competitors bundle a metronome, tone generator, and recorder because "an all-in-one practice app" feels complete | This is a personal single-user tool with an existing Discord/chat interface, not a mobile practice-room app; building real-time audio DSP (pitch detection, tempo detection) is a huge, unrelated engineering investment with no reuse of the Vault/Recall infrastructure that is this project's actual value | Recommend existing dedicated tools (a real metronome app, Modacity, a tuner) for the moment-to-moment practice room experience; this module owns the *journal and routine planning* layer only, not the practice-room instrument tooling |
| Real-time collaborative / multi-user practice tracking (bandmates, teacher-student sharing) | "Practice apps for lessons" (Better Practice, My Music Staff) are built around a teacher assigning and reviewing a student's log | PROJECT.md explicitly scopes this as a single-operator personal tool; multi-user sharing/permissioning is out of scope for the whole Sentinel project, not just this module | None needed — if a teacher relationship ever matters, it's a manual export/share of vault notes, not a built-in feature |
| Gamification beyond simple streaks (badges, levels, leaderboards, XP) | Athenify's "medals for great practice days" and similar app patterns lean into extrinsic-motivation game mechanics | For a personal tool used by one adult musician, badges/levels add UI surface and data model complexity for a motivational effect that's weak without a social/competitive audience; risks becoming a Goodhart's-Law metric people practice *for* rather than practicing well | Keep the existing simple streak counter (table stakes) and let the routine builder + history recall be the actual motivator via visible skill progress, not badges |
| Auto-transcription of played audio into notation/tab from a recording | Feels like the "ultimate" idea-capture feature — never lose a riff again, even if you didn't type it | Real audio-to-tab/notation transcription is a hard ML problem (polyphonic pitch detection, especially for guitar/bass with bends and techno production's dense multi-track material) — far outside this project's stack (Python/FastAPI, no audio ML pipeline) and would dominate the whole milestone's budget for one feature | Text-based idea capture (chord grid + freeform melody description, optionally a hummed-note sequence typed as note names) covers the "don't lose the idea" need at a fraction of the cost; if audio matters later, ListenBrainz-style *metadata* capture (what you listened to for reference) is a much cheaper proxy than transcription |
| Deep DAW integration (reading Ableton/FL project files, plugin-state capture) | Producers naturally want "log what I did in Ableton automatically" instead of manually describing the session | DAW project-file formats are proprietary/binary, version-fragile, and this project's module-isolation principle (Core doesn't import module code, modules don't reach into other apps' internals) argues against a brittle file-format integration | Freeform notes describing the production session (what was worked on: sound design, arrangement, mixing) captured the same way as an instrument practice session — the routine builder's production-workflow skill category (PART B) covers this without needing file parsing |

## Feature Dependencies

```
Practice session logging (table stakes)
    └──requires──> Vault write seam (existing, Phase 44 namespace/taxonomy)
    └──requires──> A per-instrument/skill-category taxonomy (from routine builder, PART B)

Practice-history queries ("what did I work on last week?")
    └──requires──> Practice session logging (need logged data to query)
    └──requires──> Existing Recall module / semantic search (Phase 39-41) — reused, not rebuilt

Practice streaks, aggregate summaries
    └──requires──> Practice session logging (derived purely from logged session dates/durations)

Practice-routine builder
    └──requires──> Pedagogy knowledge base per instrument/domain (PART B, seeded once, versioned as content not code)
    └──requires──> Practice-history queries (to bias routines toward neglected/plateaued skills — optional for v1, but the differentiator value comes from this link)

Structured chord-progression / melody-idea capture
    └──enhances──> Practice-routine builder (ideas can seed "workshop this progression" practice items)
    └──independent of──> Practice session logging (ideas are captured outside a specific session; a session can *reference* an idea note via wikilink, reusing existing NOTE-01..03 wikilink/graph machinery from Phase 45)

ListenBrainz listening-history pull (stretch)
    └──enhances──> Idea capture + routine builder (recently-listened reference tracks can seed "transcribe/ear-train on X" routine items)
    └──independent of──> Core logging/query features (purely additive; module functions fully without it)

Discogs wantlist / related-release suggestions (stretch)
    └──enhances──> Idea capture (a chord/melody idea can link to an inspiring release)
    └──conflicts with──> nothing; data model should hold Discogs release-id fields from day one per PROJECT.md, even if the write path ships later
```

### Dependency Notes

- **Practice-history queries require session logging:** there is nothing to query until sessions exist — but critically, this dependency is nearly free because it reuses the *existing* Recall/vault-search infrastructure (MEM-01..09, Phase 39-41) rather than needing new query machinery. This is the strongest argument for sequencing "get logging + vault schema right first" before "build history queries."
- **Routine builder requires the pedagogy KB (PART B) as content, not code:** the KB should be authored as vault-resident reference notes (or a structured seed file) so it's editable without a code change — consistent with the project's existing pattern of operator-tunable content living in the Vault (ADR-0001 precedent: persona sourced from the Vault, not hardcoded).
- **Idea capture is independent of session logging** but enhances the routine builder once both exist — sequence it in parallel with or just after core logging, not blocking on the routine builder.
- **ListenBrainz and Discogs are additive, not load-bearing:** both should be built so the module's core value (logging, history, routines) works completely without either integration ever shipping. PROJECT.md's own phrasing — "data model built to hold these fields from day one" — confirms these are schema-first, implementation-later.

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept as a genuinely useful daily-driver journal.

- [ ] Practice session logging (duration, instrument, pieces/exercises, focus area, freeform notes, mood/energy) written to `/music/practice-log/[date].md` — why essential: it's the data foundation every other feature reads from
- [ ] Structured chord-progression / melody-idea capture in `/music/ideas/` — why essential: PROJECT.md names this as a target feature and it's cheap (plain-text format, no audio) relative to its value for a producing musician
- [ ] Practice-history queries via the existing Recall/vault-search seam ("what did I work on last week", "how long on this piece") — why essential: this is the actual differentiator vs. a bare notes file, and it rides infrastructure that already exists
- [ ] Practice streaks + basic per-instrument/per-piece time rollups — why essential: table stakes, and near-zero cost once logging exists (pure derived query)
- [ ] Practice-routine builder (v1 scope: static/templated routines per instrument seeded from PART B pedagogy, not yet history-adaptive) — why essential: this is the named differentiator feature in PROJECT.md; a v1 that generates a correct, well-structured routine per instrument/skill-category is achievable without the harder "adapt to history" logic

### Add After Validation (v1.x)

- [ ] History-adaptive routine builder (bias generated routines toward neglected or plateaued skills, using the practice-history query layer) — trigger for adding: once basic routine generation and history queries are both proven correct independently, wiring them together is a natural v1.x step
- [ ] Skill-category time balance view (actual practice time vs. routine-prescribed balance) — trigger for adding: once the routine builder's skill taxonomy has stabilized and enough session history exists to make the comparison meaningful
- [ ] ListenBrainz listening-history pull — trigger for adding: once core logging/query/routine loop is validated and stable; this is explicitly a stretch feature per PROJECT.md

### Future Consideration (v2+)

- [ ] Discogs wantlist writes / related-release suggestions — why defer: explicitly a stretch in PROJECT.md; only the data model needs to exist at v1, the live write path can wait for a later milestone
- [ ] Any audio-adjacent tooling (recording, transcription, pitch/tempo detection) — why defer: identified as an anti-feature for this project's stack and scope; revisit only if a future milestone explicitly adds an audio-processing capability to the platform

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Practice session logging | HIGH | LOW | P1 |
| Practice-history queries | HIGH | MEDIUM (mostly reuse) | P1 |
| Practice streaks + rollups | MEDIUM | LOW | P1 |
| Structured idea capture (chords/melody) | HIGH | MEDIUM | P1 |
| Practice-routine builder (templated v1) | HIGH | HIGH | P1 |
| History-adaptive routine builder | HIGH | HIGH | P2 |
| Skill-category time balance view | MEDIUM | MEDIUM | P2 |
| ListenBrainz listening-history pull | MEDIUM | MEDIUM | P2 |
| Discogs wantlist / related-release suggestions | LOW–MEDIUM | MEDIUM | P3 |
| Audio recording/tuner/metronome tooling | LOW (duplicates existing tools) | HIGH | Not planned (anti-feature) |
| Audio-to-notation transcription | MEDIUM | VERY HIGH | Not planned (anti-feature) |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Modacity / Andante / Instrumentive (commodity practice apps) | iReal Pro (chord-chart specialist) | Our Approach |
|---------|---------------------------------------------------------------|--------------------------------------|--------------|
| Session logging | Native, form-based, app-siloed | N/A | Chat-native logging, vault-persisted, cross-linked to the rest of the second brain |
| History queries | Basic charts/streaks within the app only | N/A | Full natural-language recall via existing semantic Vault search — no other practice app offers this |
| Chord/idea capture | Not a focus (session notes only) | Core product; proprietary URL-encoded chord-grid format, closed ecosystem | Open plain-text, iReal-Pro-*inspired* chord-grid notation stored as ordinary markdown/frontmatter — interoperable with the rest of the vault, not locked to one app |
| Routine generation | None of the reviewed apps generate routines from pedagogy — user supplies their own plan | N/A | Differentiator: pedagogy-informed routine builder (PART B) — no competitor analyzed does this |
| Cross-domain context | None — practice apps are single-purpose silos | N/A | Practice sessions live in the same graph as journal/session notes and other modules (Pathfinder, etc.) — the core value proposition of building this as a Sentinel module rather than adopting a commodity app |

---

## PART B — Practice Pedagogy Knowledge Base (for the Routine Builder)

This section is the content seed for the routine builder. Each instrument/domain is broken into named skill categories consistent with the "skill-category time balance" differentiator above, with concrete drills/progressions the builder can slot into a generated session. Sourced from multiple independent, converging pedagogy sources per category (see per-claim citations in the digests cached to research-store; representative named sources below).

### Cross-Instrument Principles (apply to every routine)

1. **Deliberate practice over passive repetition.** Practice must be actively self-supervised: listen critically in real time and/or record yourself, and identify exactly what went wrong on a mistake rather than blindly repeating (Bulletproof Musician / Noa Kageyama; converges with the general deliberate-practice literature, e.g. Ericsson). The routine builder should always pair a drill with an explicit "what to listen for" instruction, not just a duration.
2. **Spaced repetition within a session.** Interleave 2-4 short tasks and return to each one after a few minutes rather than grinding one task to exhaustion (blocked repetition). This is standard advice across piano, guitar, and general practice-methodology sources (Modacity blog, Piano Practice Assistant). The builder should generate routines as *rotations* of short blocks, not single long blocks per skill.
3. **Spaced repetition across days — the 24-48-72 rule.** Revisit new material the next day, then 2 days later, then increasingly spaced out, extending the interval each time recall succeeds. This is directly implementable: the routine builder can use logged session history to know when a piece/idea/skill was last touched and schedule its next appearance.
4. **Slow-to-fast tempo progression via metronome, universally.** Every instrument source converges on: start at a tempo where the passage is 100% clean, and increase in small increments (2-5 BPM) only after 2-3 clean repetitions; drop back on a miss. A "practice below target tempo" phase (50-55% of goal tempo) builds relaxed technique before speed work. This is a directly generatable drill parameter: `{passage, start_bpm, target_bpm, increment_bpm, clean_reps_required}`.
5. **Named skill categories, not just "practice."** Every instrument routine should be composed from a small fixed taxonomy so time-balance tracking (PART A differentiator) is meaningful: **Technique**, **Repertoire/Vocabulary**, **Ear Training**, **Theory**, and (for production-facing instruments) **Production Workflow**. A generated routine allocates minutes across these categories rather than treating "practice" as one undifferentiated block.

### Electric Guitar

- **Session shape** (D'Addario Lesson Room, Guitar Player, Premier Guitar): ~10 min warmup, ~10 min technique, ~10 min scales, ~20 min repertoire/songs, ~10 min reading — roughly a 50/50 split between mechanics (warmup+technique+scales) and musical application (repertoire+reading).
- **Warmup drills:** chromatic scale runs across all four fingers (alternate picking and hammer-on/pull-off variants), cycling through open-chord shapes for rhythm players. Keep warmups no harder than the session's actual workload — a warmup that's itself a stretch/speed challenge defeats the purpose.
- **Technique drills:** scale/arpeggio/chord-shape isolation at a clean, slow metronome tempo, using the universal slow-to-fast progression above (increment_bpm ≈ 2-5).
- **Repertoire:** apply spaced repetition across days to songs/pieces in progress; a "reading" block (sight-reading tab/notation) rounds out the session.
- **Suggested method-book/tool lineage to seed drill content from** (well-known, not deep-linked here — routine builder authors can pull specific exercises): chromatic/alternate-picking exercise books (e.g. *Guitar Aerobics*-style daily exercise structure), speed-building method books built around metronome progression (e.g. Troy Stetina's *Speed Mechanics for Lead Guitar*), standard scale/arpeggio/CAGED-shape vocabulary.

### Electric Bass

- **Session shape** (Scott's Bass Lessons, Berklee Take Note, Mastertemps): 5-10 min warmup (fretboard runs / a favorite riff), 10-15 min play-along on a backing track (groove and timing in a real musical context, not isolated drills), 10-15 min theory + ear training.
- **Bass-specific priority: ear training over generic scale drilling.** Sources are explicit that "big ears" — hearing root movement, feeling harmonic changes, recognizing phrase lengths — is the bassist's core differentiator skill, more so than for melodic-lead instruments. The routine builder should weight Ear Training higher for bass than for lead guitar.
- **Groove/technique drills:** always practiced *in time* against a backing track or drum loop, not purely mechanical isolation — bass technique's stated purpose is "expression, not perfection" (i.e. groove feel, not just clean note execution).
- **Transcription** (learning a bassline by ear from a recording) is treated as a core learning method, not an advanced add-on — should appear as a regular routine item, not gated behind an "advanced" tier.

### Synthesizer / Sound Design

- **Core drill: patch recreation by ear.** Reproduce a known/commercial patch (or an iconic sound from a track the user knows) on a synth, working purely by listening rather than reading a preset — this is the sound-design equivalent of ear training and ties directly to the "Ear Training" skill category (MusicTech, ModWiggler forum consensus).
- **Cross-synth translation drill:** recreate a patch from one synth engine in a different synth engine to force comparison of parameters and signal-flow reasoning — builds transferable sound-design vocabulary rather than one-tool-specific muscle memory.
- **Context, not isolation.** Design patches against a running drum beat/track rather than soloed — soloed patch design produces overly frequency-rich, mix-incompatible sounds. This is a Production Workflow-category constraint the builder should bake into every synth drill: "load against a reference loop before finalizing."
- **Named training tool for calibration:** Syntorial (ear-to-synthesis-parameter training) is a purpose-built precedent for this category — useful as a reference point for drill difficulty progression (start with single-oscillator/simple-filter patches, progress to multi-oscillator/modulation-heavy patches).

### Piano / Keys

- **Session shape:** 5 min warmup/stretching, daily scale work (major/minor) plus dexterity drills (Hanon-style), 5-10 min sight-reading at a fixed slow metronome tempo, repertoire practiced hands-separately then combined, dedicated ear-training block. Recommended session length 30-60 min/day; repertoire pace ~1-2 new pieces/week at 15-30 min/session invested.
- **Repertoire method:** hands-separate first, then hands-together only once each hand is clean; combine at a tempo slow enough to have zero (or very few) mistakes before applying the universal slow-to-fast progression.
- **Sight-reading:** a dedicated, separate short block (not folded into repertoire) using material *easier* than current repertoire level, at a fixed slow metronome tempo — volume of varied material matters more than difficulty for this skill.
- **Ear training:** interval and chord identification (tool-assisted, e.g. EarMaster-style apps) plus singing repertoire/popular melodies to internalize pitch relationships — singing is called out specifically as accelerating pitch-relationship internalization.
- **Named method-book lineage:** Hanon (finger-independence/dexterity), standard major/minor scale-and-arpeggio curricula, sight-reading graded-material series — routine builder can generate scale/Hanon-style drill sequences without needing copyrighted material, just the progression logic (key rotation, hands-separate-then-together, metronome ramp).

### Sampler / Sampling (as a performable instrument)

- **Core reframe: sampling is a practiced instrumental skill, not a production shortcut** (MusicRadar, Audeobox, Melodics). Treat pad-mapping and chopping with the same seriousness as fretboard technique.
- **Drill 1 — chop-and-map:** take a sample (vocal, break, one-shot library), chop it (transient-detection slicing or manual), and map segments logically across pads/keys for playability — practice *playing* the resulting instrument, not just building it once.
- **Drill 2 — pad performance / muscle memory:** once a sample kit is mapped, practice playing rhythmic patterns on the pad grid the way a drummer practices rudiments — named professional precedent is MPC-style "played" sampling performance (e.g. Araabmuzik) rather than sequenced/step-entered patterns.
- **Progression scheme:** start with simple 4-8 pad layouts and short rhythmic patterns, progress to full-kit layouts (multi-velocity, multi-articulation) and longer improvised pad performances — mirrors the technique-drill slow-to-fast/simple-to-complex progression used on other instruments, just measured in pad-count/pattern-complexity instead of BPM.

### Music Production for EDM / Techno / Melodic Techno

- **Treat as (at least) three separate, practicable skill tracks, not one "make a track" blob:** Sound Design, Arrangement, and Mixing (Myloops, EDM Tips, Beatportal guides converge on this separation). The routine builder should generate production-focused sessions that pick ONE of these per session rather than always attempting a full track.
- **Arrangement-specific pedagogy:** melodic-techno arrangement is explicitly framed as building an emotional journey — build and release tension across sections; a common named pitfall is revealing the best melodic material too early (in the intro) instead of saving it to reward the first breakdown. A generated "arrangement practice" drill can be: take an existing loop/idea and practice building 2-3 different arrangement structures from it without writing new sound design, to isolate the arrangement skill from sound-design skill.
- **Mixing-specific pedagogy:** the identified common mistake is treating mixing as a final pass after arrangement is "done" — sources recommend mixing concurrently with sound design and arrangement. A generated "mixing practice" drill can target one technique at a time (e.g. a compression-only pass, a reverb/delay-space-only pass) on an existing rough mix, rather than a full mix pass.
- **Sound-design practice** for this genre reuses the general Synthesizer section above, with the added constraint of designing against a 4-on-the-floor groove/reference loop (techno's structural backbone) rather than an arbitrary beat.
- **Relationship to sampler/synth skill categories:** production-track sessions should be generatable as a *composite* of the Sampler and Synthesizer skill categories above plus the Arrangement/Mixing categories unique to this section — i.e., production is where the instrument-specific skill categories converge into a session, not a wholly separate taxonomy.

### Ear Training (cross-instrument, but especially load-bearing for bass/synth/production)

- **Structured session shape:** a ~20-minute block splits roughly into intervals (5 min) → chord identification (5 min) → transcription/melodic dictation (5-10 min) → singing (5 min). This maps cleanly to a generatable routine block with fixed sub-durations.
- **Progression path:** simple intervals → complex intervals → triads/inversions → functional chord progressions, starting with the most common progression (I-IV-V) before generalizing. This gives the routine builder a clear difficulty-ramp axis independent of instrument.
- **Transcription** (learning a real recording by ear) is the practical capstone of ear training across every instrument section above (guitar, bass, synth-patch-recreation are all specific applications of the same underlying skill) — the routine builder can treat "transcribe X" as a single generic drill type parameterized by instrument and source material.
- **Tools named as precedent** (for calibrating drill difficulty/format, not for integration): Functional Ear Trainer, Perfect Ear, Tenuto, musictheory.net-style interval/chord drill apps.

## Sources

**PART A (product/feature landscape):**
- [Andante Music Practice Journal](https://andante.app/) — session logging, mood/focus, streaks
- [Modacity — Music Practice Journal & Companion](https://www.modacity.co/) — integrated practice toolkit
- [Instrumentive for Musicians (Google Play)](https://play.google.com/store/apps/details?id=com.instrumentive.musicnotes&hl=en_US) — per-piece time tracking, aggregate charts
- [Legato: Music Practice Journal (Google Play)](https://play.google.com/store/apps/details?id=com.proximitylabs.legato&hl=en_US) — streaks, stats
- [Athenify Music Practice Tracker](https://athenify.io/music-practice-tracker-app) — per-technique time balance, medals
- [Practis — Music Practice Tracker, Timer & Metronome](https://pract.is/) — history/goals/reports
- [Best Apps to Track Your Music Practice Time (Practis Blog)](https://pract.is/blog/best-apps-to-track-your-music-practice-time-5-options-compared)
- [Better Practice — teacher/student practice logs](https://betterpracticeapp.com/)
- [iReal Pro custom chord chart protocol](https://www.irealpro.com/ireal-pro-custom-chord-chart-protocol) — chord-progression text-encoding prior art
- [ListenBrainz API — Core listens endpoint](https://listenbrainz.readthedocs.io/en/latest/users/api/core.html) — official docs
- [Discogs API — Collection/Wantlist documentation](https://www.discogs.com/developers/) — official docs

**PART B (pedagogy):**
- [Bulletproof Musician — practice hack / deliberate self-supervision](https://bulletproofmusician.com/a-practice-hack-that-could-significantly-boost-practice-efficiency-but-may-not-feel-like-it-in-the-moment/)
- [Modacity Blog — Using Spaced Repetition to Achieve Effective Practice](https://www.modacity.co/blog/using-repetition-achieve-effective-practice)
- [Piano Practice Assistant — spaced repetition for musicians](http://pianopracticeassistant.com/spaced-repetition/)
- [D'Addario Lesson Room — Creating a Practice Routine for Electric Guitar](https://www.daddario.com/the-lesson-room/guitar/electric-guitar/teach/creating-a-practice-routine/)
- [GuitarPlayer — Warm-Up Time: 11 Exercises](https://www.guitarplayer.com/lessons/warm-up-time-11-exercises-that-will-help-you-play-even-better)
- [Premier Guitar — Essential Guitar Warm-Up Exercises](https://www.premierguitar.com/lessons/guitar-warm-ups)
- [Scott's Bass Lessons — 10 Tips to Improve Your Bass Practice Routine](https://scottsbasslessons.com/blog/10x-your-practice-results-the-how-and-the-what)
- [Berklee Online Take Note — How to Practice Bass Effectively](https://online.berklee.edu/takenote/bass-players-how-to-practice-bass-effectively-pt1/)
- [Mastertemps Bass Blog — Developing a Practice Routine](https://mastertempsbassblog.com/how-to-practice-bass-guitar/)
- [MusicTech — Practice sound design by recreating synth patches](https://musictech.com/tutorials/weekend-workshop-practice-your-sound-design-by-recreating-synth-patches/)
- [Soundfly — Advanced Synths and Patch Design for Producers](https://soundfly.com/courses/advanced-synths-and-patch-design)
- [Syntorial — Learn Synthesizer Programming](https://www.syntorial.com/learn-more/)
- [Traipsing About — Creating a Solid Piano Practice Routine](https://www.traipsingabout.com/p/creating-a-solid-piano-practice-routine)
- [Piano Wizard Academy — Effective Piano Practice Techniques](https://pianowizardacademy.com/music-learners/effective-piano-practice-techniques-for-rapid-progress/)
- [Fundamentals of Piano Practice — The Practice Routine](https://fundamentals-of-piano-practice.readthedocs.io/chapter1/ch1_procedures/II.1.html)
- [MusicRadar — MPC-style sampling tricks using Ableton Push 2](https://www.musicradar.com/tuition/tech/how-to-perform-mpc-style-sampling-tricks-using-ableton-push-2-643660)
- [Audeobox — Ableton Simpler & Sampler Complete Guide](https://www.audeobox.com/learn/ableton/simpler-sampler-complete-guide/)
- [Melodics — Master the Art of Sampling](https://melodics.com/blog/beginner-guide-to-sampling)
- [Myloops — Melodic Techno Production: Complete Guide](https://www.myloops.net/melodic-techno-production-complete-guide-from-start-to-finish)
- [EDM Tips — How to Make Melodic Techno](https://edmtips.com/how-to-make-melodic-techno/)
- [Beatportal — Step-by-Step Guide to Melodic House & Techno](https://www.beatportal.com/articles/899368-step-by-step-guide-to-creating-a-melodic-house-techno-track-anyma-miss-monique-artbat-stephan-bodzin)
- [Plugin Music School — How to Mix Techno Like a Pro](https://www.pluginmusicschool.com/mixing-how-to-do-mixing-like-a-pro/)
- [Bounce Metronome — Accelerating Tempo Gradually](https://www.bouncemetronome.com/features/tempo/gradually-faster-or-slower)
- [The Online Metronome — How To Practice With A Metronome](https://theonlinemetronome.com/blogs/14/practice-with-a-metronome)
- [MusiciansTool — Metronome Practice Secrets](https://musicianstool.com/blog/metronome-practice-secrets)
- [MusicTheory.xyz — Ear Training for Musicians](https://musictheory.xyz/ear-training)
- [The Music Theory Professor — Ear Training 101](https://themusictheoryprofessor.com/ear-training-101-how-to-hear-intervals-chords-and-progressions-like-a-pro/)
- [Ear training — Wikipedia](https://en.wikipedia.org/wiki/Ear_training)

---
*Feature research for: Music Lesson Tracker module (v0.6.0 milestone)*
*Researched: 2026-07-08*
