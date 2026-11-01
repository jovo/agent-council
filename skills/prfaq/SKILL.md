---
name: prfaq
description: Line-by-line checklist for writing and reviewing an Amazon-style PR/FAQ (a future press release plus FAQ), including platform and marketplace launches. Use whenever the task drafts, edits, restructures, or reviews a PR/FAQ, a launch press release, its headline or subhead, or its FAQ, or asks how an Amazon executive would judge one.
---

# PR/FAQ

A PR/FAQ is a press release for a product that does not exist yet, written from its launch date, followed by the questions a customer and a decision maker will ask. The press release fits on one page. If it cannot make the hero customer want the product, the product changes before the document does.

Sources for the structure:

- Ian McAllister's 2012 Quora answer on Amazon's internal press releases, summarized with his section list by [Mequoda](https://www.mequoda.com/articles/audience-development/an-inspirational-press-release-template-from-amazon).
- Colin Bryar and Bill Carr, [Working Backwards PR/FAQ Instructions & Template](https://workingbackwards.com/resources/working-backwards-pr-faq/), and their book *Working Backwards* (St. Martin's Press, 2021).
- AWS, [Product Management at Amazon](https://aws.amazon.com/executive-insights/content/product-management-at-amazon/), which says the press release "must fit on a single page."

McAllister and Bryar and Carr give the same press release order: heading, subheading, summary, problem, solution, then quotes and getting started, then the closing. Bryar and Carr group the spokesperson quote, the customer quote, and getting started as one block. McAllister orders them spokesperson quote, getting started, customer quote, and this skill follows him. Neither template has a separate proof paragraph, partner quote, or price section. Each check below comes from one of these sources, except the no-price rule, which is Yumzu's.

Use the checklist two ways. Authors tick it while drafting. Reviewers report each unmet item as a finding in the `unified-review` format (severity groups, inline diffs). The `logic` skill still applies to the argument, and CLAUDE.md's writing rules still apply to every sentence.

## Before drafting

- [ ] **Hero customer.** One precisely defined customer segment, named as a role ("the grower who owns the arm"), not a segment list. Bryar and Carr: "If you think your product is for everyone, you are mistaken." Everyone else is supply, channel, or partner.
- [ ] **One PR/FAQ per side.** A product with two kinds of customer can need two PR/FAQs. Fulfillment by Amazon had one from the seller's side and one from the buyer's. For a marketplace, decide whether the supply side (creators, developers, sellers) needs its own.
- [ ] **The most important problem.** Of the problems the product could solve, the one that matters most to the hero, and one with enough customers willing to pay to make the market worth entering.
- [ ] **Today's alternatives.** What the hero uses now to deal with the problem, and why it falls short. There is always a current solution.
- [ ] **The one differentiator.** How the product is better, faster, or cheaper than those alternatives, in language the customer understands, with no corporate jargon (Bryar and Carr). If it solves the problem the way existing products do, go back to the drawing board.
- [ ] **Launch scope and date.** What ships, for which hardware, markets, or accounts, on a date the team expects to launch. What does not ship is for the FAQ.

## Press release, line by line

Write the elements in this order. Each item names what the element must do, then what to check.

### 1. Heading

- [ ] Names the product so the target customer understands it: "[Company] Launches [Product]: [what the hero now gets]."

### 2. Subheading

- [ ] One sentence. Both templates say so.
- [ ] Names the customer segment precisely and the benefit they gain.

### 3. Summary paragraph

- [ ] Opens with the city, the media outlet, and the launch date: "BERKELEY, Calif. (BUSINESS WIRE), November 14, 2028:" or the outlet's own dateline style.
- [ ] Summarizes the product and its benefits. Assume the reader reads nothing else. A reader who stops here knows what launched, for whom, what it does for them, and where to get it.

### 4. Problem paragraph

- [ ] The problem, from the customer's point of view, with what it costs them.
- [ ] The most important problem, not a list. If the draft argues two problems, pick the one the hero would pay to solve and move the other to the FAQ or the solution.
- [ ] Comes before the solution.

### 5. Solution paragraph(s)

- [ ] Describes the product in enough detail to show how it simply and directly solves the problem in element 4. More than one paragraph is fine for a complex product.
- [ ] Addresses the stated problem, not other needs. A laundry list of features that do not touch the problem gets cut.
- [ ] **Names today's alternatives.** Bryar and Carr: the solution paragraph "should include: 'Today, customers with this problem use x, y, or z products to meet their needs. Those products fall short of solving x problem(s). Our product addresses these unmet needs in the following ways.'" The solution paragraph contains a sentence of that form, naming the specific alternatives, how each falls short, and how the product addresses that gap. A draft that mentions competitors elsewhere, or only in the FAQ, fails this check.
- [ ] Clear and brief. Long, vague, or high-level descriptions fail.

### 6. Spokesperson quote

- [ ] One quote from the company's spokesperson.

### 7. How to get started

- [ ] Shows how easy it is to start: the steps, in order, with who does each and how long it takes.

### 8. Customer quote

- [ ] One quote from a hypothetical customer, in the hero's voice, describing how they experienced the benefit, in words they would use.

### 9. Closing and call to action

- [ ] Wraps up and points the reader to where to learn more and get started, with a link.
- [ ] **No price** (Yumzu's rule). Neither template has a price section, and Bryar and Carr make "What is the price?" the first External FAQ. Price, all in, goes there, as do platform revenue splits.

## Whole release

- [ ] Fits on one page.
- [ ] One hero, one segment.
- [ ] Two quotes: the spokesperson and the customer.
- [ ] No jargon the hero would not use: replace "catastrophic forgetting," "TCP," "pipeline," "ecosystem" with what they mean for the customer.
- [ ] No price or revenue split anywhere in the release, quotes included (Yumzu's rule). Savings stated as an outcome (22% less per part) can stay.
- [ ] Reads as written for the customer, not for investors. Bryar and Carr: the release ignores "competitors, current capabilities, P&L, business partners." Business-model detail moves to the FAQ.

## FAQ

The FAQ has no fixed length. External questions come first, then internal ones. Put the most important questions first in each, and leave out questions that do not change the decision (AWS: the team does not "include every possible question"). Bryar and Carr list standard questions on the [Working Backwards page](https://workingbackwards.com/resources/working-backwards-pr-faq/), Appendix 2. The ones below cover theirs and the questions AWS names.

### External FAQ (first)

Questions customers and the press will ask, in language they understand.

- [ ] What is the price, all in, and what does it replace?
- [ ] How does it work?
- [ ] What do I need before I start, and who installs it?
- [ ] How do I get help or support, and what happens when it fails?
- [ ] Where can I buy it?
- [ ] Will my data be secure? (AWS)

### Internal FAQ (second)

Questions senior leaders and every department (finance, marketing, support, operations, HR, legal) will ask after reading the release.

- [ ] What does the target customer use today, who are the competitors, and how is this better, faster, or cheaper?
- [ ] Market size: how many customers have the problem, how many will pay to solve it, how much, and how many can use the product. Each figure sourced, arithmetic shown.
- [ ] Per-unit economics: gross profit and contribution profit per unit, and what has to be true for them to hold.
- [ ] Upfront investment (people, technology, inventory, space), how the team manages that risk, and months or years to profitability.
- [ ] The hard problems to solve (business model, engineering, legal, UI), the hardest technical risk, and the evidence it is solved.
- [ ] New capabilities the company must build.
- [ ] Third-party relationships and technologies the product depends on, why each partner will commit, and what each has committed to by launch.
- [ ] Regulatory and legal issues.
- [ ] What must be true for the product to succeed, and the top three reasons it will not.
