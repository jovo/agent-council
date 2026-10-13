---
name: logic
description: Check and build the logic of an argument at every scale, from the document's arc to a single sentence. Use whenever the task drafts, outlines, restructures, or reviews a paper, proposal, memo, report, section, paragraph, or analysis, and whenever the user asks whether an argument holds, flows, or follows.
---

# Logic

Logic comes first. A draft whose steps do not follow fails however well it reads, so check the argument before style. The rules on precise claims (universals, comparisons, hedges, necessity) in CLAUDE.md's "Writing and review guidelines" still apply. This skill says how to test that each step follows from the last. For claims drawn from data, the `statistics` skill checks whether the design and analysis support them.

## The document's arc

- State the central claim in one sentence before judging anything else. If the draft does not support one, that is the first finding.
- Then state the story's four elements, OCAR (Schimel, *Writing Science*, 2012), one sentence each: the opening (the larger problem), the challenge (the specific question), the action (what was done and found), and the resolution (how understanding changed). The `papers-and-proposals` skill defines them. Check that the challenge is a question, not a list of objectives, that the action addresses that question, that the resolution answers it, and that the resolution returns to the opening's problem. A missing element or a resolution that answers a different question is a broken arc.
- The opening and the resolution have the same scope. An opening wider than the resolution promises more than the work delivers. One narrower hides who should care.
- Every section supports or qualifies the central claim. A section that does neither is a digression: cut it or say what it supports.
- The question does not presuppose its answer or its method. "How does X cause Y?" assumes X causes Y.
- The gap is the current best approach plus the one limit that makes it inadequate. "Current methods are insufficient" is not a gap. The contribution addresses that named limit, or the argument does not connect.
- Each central claim names the observation that would confirm or refute it. A claim that no observation could refute does no work.
- The claim matches what the evidence licenses, in both directions. Flag overclaims, and flag underclaims: a design that supports a broader claim than the draft makes.
- For each central claim, name the competing explanation a skeptical reader would raise, and say what in the draft rules it out. If nothing does, that is a gap in the argument, not a matter of style.
- Order follows dependence. Nothing is used before it is defined or argued, and no conclusion appears before its premises.

## Sections

- Each section opens with the question it answers and ends with the answer.
- That answer is a premise the next section uses. If the next section does not use it, either the order is wrong or one of the sections is a digression.

## Paragraphs

- Each paragraph carries one idea. By default, state it in the first sentence (topic sentence, then development). Every later sentence develops it: it follows from the one before or supports that idea.
- At a turn in the story, such as the challenge at the end of an introduction or the resolution at the end of a discussion, a paragraph can follow OCAR itself and put its point last: the first sentence sets up the question and the last sentence answers it. Use point-last paragraphs only at those turns. In either form, the point sits in the first or last sentence, never buried in the middle.
- A "so", "therefore", "thus", or "hence" needs its premise on the page. A conclusion whose premise is missing is a leap.
- The last sentence leads to the next paragraph's idea. Two adjacent paragraphs with no link between them are a break in the argument.

## Sentences

- Each sentence is a small story: a short topic that links to what came before, its main verb soon after, and the new or important information at the end, the stress position. The next sentence picks up that stress as its topic.
- Each connective asserts a relation, and the relation has to hold. "Because" asserts a cause, "so" a consequence, "but" and "although" a contrast. "A, so B" where B does not follow from A is a non sequitur, however smooth it reads.
- Quantifiers and modals say exactly what the evidence supports: some, most, or all; can, does, or must.
- Give each concept one name and use it everywhere. A term that drifts in meaning between premise and conclusion breaks the inference.
- Use the field's existing term and notation, or say why you depart from it.
- Name the referent of "this", "it", or "they" when more than one noun could fit.

## Reporting a logic finding

- Name the step that fails and the kind of failure: missing premise, non sequitur, circular setup, unaddressed alternative, overclaim, underclaim, term drift, order, or a broken arc (a missing OCAR element, objectives in place of a question, or a resolution that answers a different question than the challenge).
- State the missing premise explicitly. Then give the fix: either the sentence that supplies the premise, or the weaker conclusion that no longer needs it. "Unclear" alone is not a finding. When the missing premise depends on a decision the draft has not made, ask the author which premise holds and name the options, in place of supplying one.
- Severity: a broken step in the central argument is Critical. A leap in a supporting point is Substantive. A connective or referent that blurs a step that does hold is Nitpick.
