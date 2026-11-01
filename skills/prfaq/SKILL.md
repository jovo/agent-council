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

McAllister and Bryar and Carr give the same press release order: heading, subheading, summary, problem, solution, then quotes and getting started, then the closing. Bryar and Carr group the spokesperson quote, the customer quote, and getting started as one block. McAllister orders them spokesperson quote, getting started, customer quote, and this skill follows him. Neither template has a separate proof paragraph, partner quote, or price section. Checks marked *(house)* go beyond those sources and come from reviewing drafts in this house style.

Use the checklist two ways. Authors tick it while drafting. Reviewers report each unmet item as a finding in the `unified-review` format (severity groups, inline diffs). The `logic` skill still applies to the argument, and CLAUDE.md's writing rules still apply to every sentence.

## Before drafting

- [ ] **Hero customer.** One precisely defined customer segment, named as a role ("the grower who owns the arm"), not a segment list. Bryar and Carr: "If you think your product is for everyone, you are mistaken." Everyone else is supply, channel, or partner.
- [ ] **One PR/FAQ per side.** A product with two kinds of customer can need two PR/FAQs. Fulfillment by Amazon had one from the seller's side and one from the buyer's. For a marketplace, write the hero's release first *(house)*, then decide whether the supply side (creators, developers, sellers) needs its own.
- [ ] **The most important problem.** Of the problems the product could solve, the one that matters most to the hero, and one with enough customers willing to pay to make the market worth entering.
- [ ] **Today's alternatives.** What the hero uses now to deal with the problem, and why it falls short. There is always a current solution.
- [ ] **The one differentiator.** How the product is better, faster, or cheaper than those alternatives, in the customer's words, not the mechanism *(house)*: "switches tasks without forgetting old ones," not "continual learning." If it solves the problem the way existing products do, go back to the drawing board.
- [ ] **The CFO sentence** *(house)*. One sentence the hero would repeat to whoever approves the purchase. It names an outcome they pay for: money, time, idle capacity, risk.
- [ ] **Launch scope and date.** What ships, for which hardware, markets, or accounts, on a date the team expects to launch. What does not ship is for the FAQ.
- [ ] **Evidence the hero exists** *(house)*. A Customer Zero, pilot, or design partner whose numbers the release can cite. If the only evidence is in another vertical, that vertical is the hero.

## Press release, line by line

Write the elements in this order. Each item names what the element must do, then what to check.

### 1. Heading

- [ ] Names the product so the target customer understands it: "[Company] Launches [Product]: [what the hero now gets]."
- [ ] **Benefit, not mechanism** *(house)*. Ask of each clause: does it say what the customer does or what the product is, or what the customer gets? "Unlock a marketplace," "download skills," and "AI-powered" are mechanism. "Switches tasks in minutes" is benefit.
- [ ] **Prerequisites** *(house)*. If the benefit depends on buying or installing something first, the heading says so ("Add One Device, and..."), so a time claim like "in minutes" attaches to the repeated step, not the purchase.
- [ ] Uses the product's own terms *(house)*. If the store is the Skill Store, the unit is a skill, not a "job" or a "cartridge."
- [ ] No absolutes the evidence cannot back *(house)*: "never," "every," "any."
- [ ] No filler verbs *(house)*: unlock, empower, revolutionize, transform.

### 2. Subheading

- [ ] One sentence. Both templates say so.
- [ ] Names the customer segment precisely and the benefit they gain.
- [ ] Carries the CFO sentence if the heading does not.
- [ ] States each feature as what the customer gets *(house)*. "Runs on the device" is mechanism. Its benefit (works without a network, data stays on site, no cloud fees) is a separate claim, so pick the one you will stand behind or cut it.
- [ ] Does not repeat the heading in other words *(house)*.

### 3. Summary paragraph

- [ ] Opens with the city, the media outlet, and the launch date: "BERKELEY, Calif. (BUSINESS WIRE), November 14, 2028:" or the outlet's own dateline style.
- [ ] Summarizes the product and its benefits. Assume the reader reads nothing else. A reader who stops here knows what launched, for whom, what it does for them, and where to get it.
- [ ] Introduces each product term once, defined by what it does *(house)* ("a Knowledge Cartridge, a downloadable skill certified for a standard workcell").
- [ ] The hero is the actor *(house)*. Name the role ("growers browse the store"), not a generic "operators" or "users."

### 4. Problem paragraph

- [ ] The problem, from the customer's point of view, with what it costs them.
- [ ] The most important problem, not a list. If the draft argues two problems, pick the one the hero would pay to solve and move the other to the FAQ or the solution.
- [ ] Comes before the solution, and before safety or compliance detail *(house)*. The reader learns why to care first.
- [ ] Scale numbers are about the hero's market, not an adjacent one *(house)*. A global count that is mostly another industry misleads.
- [ ] Market facts presented as true today have a source in the FAQ *(house)*. Invented launch metrics are fine, since the release is fiction about the future.

### 5. Solution paragraph(s)

- [ ] Describes the product in enough detail to show how it simply and directly solves the problem in element 4. More than one paragraph is fine for a complex product.
- [ ] Addresses the stated problem, not other needs. A laundry list of features that do not touch the problem gets cut.
- [ ] **Names today's alternatives.** Bryar and Carr's pattern: "Today, customers with this problem use x, y, or z. Those products fall short of solving x. Our product addresses these unmet needs in the following ways." This is where the differentiator shows.
- [ ] Clear and brief. Long, vague, or high-level descriptions fail. Mechanism appears only as far as the reader needs it to believe the benefit *(house)*. Architecture belongs in the FAQ.
- [ ] Says nothing twice *(house)*. Two paragraphs that each walk through "download, calibrate, run" merge into one.
- [ ] **Platform launches** *(house)*. Other sides of the platform (creators, developers, integrators, data contributors) appear as the reason the hero gets more over time, in a sentence or two. Their economics go in the FAQ, and their own story goes in their own PR/FAQ.
- [ ] **The platform contract** *(house)*. If the platform works only under a standard (a published spec, an API, a certified configuration), name it once, plainly. It is what lets the sides work together, so it is not fine print.
- [ ] Safety, compliance, and certification claims say what the product does and what the customer or installer still owns *(house)*. "Guarantees compliance" is a claim legal will strike if compliance belongs to the installed system.

### 6. Spokesperson quote

- [ ] One quote from the company's spokesperson.
- [ ] Says why the customer is better off, in plain words *(house)*. Not a lecture on the technology.
- [ ] No false universals *(house)* ("every animal brain learns without forgetting"). State the bounded claim.
- [ ] Consistent with the product as described *(house)*. A quote that says "chip" when the body says "edge computer" is two different companies.

### 7. How to get started

- [ ] Shows how easy it is to start: the steps, in order, with who does each and how long it takes.
- [ ] Prerequisites (hardware, accounts, installer) are explicit *(house)*.
- [ ] Time claims match each other *(house)*. "Minutes" for a skill and "days" for a cell build can both hold if the release says which is which.

### 8. Customer quote

- [ ] One quote from a hypothetical customer, in the hero's voice, describing how they experienced the benefit, in words they would use.
- [ ] **Pilot story** *(house)*. If a Customer Zero or pilot exists, its story belongs here, as a short lead-in to the quote, not as its own section. It names the customer (placeholder if real names cannot circulate), gives before and after numbers on the hero's outcome, and shows the differentiator as a sequence, not a single metric (crop A, swap to crop B, back to A at prior accuracy).
- [ ] **Physical feasibility** *(house)*. Every part the story needs exists in the product or is named as the customer's. If a fixed arm works "across greenhouses," something moved it.
- [ ] Metrics are defined well enough to check *(house)* (picks per hour including or excluding travel), and numbers agree within the paragraph (38% per pound versus "nearly 40%" per crate needs one unit).
- [ ] Mentions only what the release already introduced *(house)*. A third crop that appears only in the quote raises a question the release never answers.

### 9. Closing and call to action

- [ ] Wraps up and points the reader to where to learn more and get started, with a link.
- [ ] **No price** *(house)*. Neither template has a price section, and Bryar and Carr make "What is the price?" the first External FAQ. Price, all in, goes there, as do platform revenue splits.

## Whole release

- [ ] Fits on one page.
- [ ] One hero, one segment. Other verticals get one clause or move to the FAQ *(house)*.
- [ ] Two quotes: the spokesperson and the customer. A partner, creator, or channel quote belongs in that side's own PR/FAQ *(house)*.
- [ ] Each concept has one name, used everywhere *(house)* (skill, cartridge, Knowledge Cartridge: pick one or define how they relate).
- [ ] No jargon the hero would not use: replace "catastrophic forgetting," "TCP," "pipeline," "ecosystem" with what they mean for the customer.
- [ ] No puffery labels *(house)*: "premier," "leading."
- [ ] No price or revenue split anywhere in the release, quotes included *(house)*. Savings stated as an outcome (22% less per part) can stay.
- [ ] Every number appears once or agrees everywhere it appears *(house)*.
- [ ] No claim the company cannot defend in front of legal, safety, or a skeptical customer *(house)*: absolutes, guarantees, "unbypassable."
- [ ] Real companies and named people in invented quotes are replaced with placeholders before the document leaves the team *(house)*.
- [ ] Reads as written for the customer, not for investors. Bryar and Carr: the release ignores "competitors, current capabilities, P&L, business partners." Business-model detail moves to the FAQ.

## FAQ

The FAQ has no fixed length. External questions come first, then internal ones. Put the most important questions first in each, and leave out questions that do not change the decision. Bryar and Carr list standard questions on the [Working Backwards page](https://workingbackwards.com/resources/working-backwards-pr-faq/), Appendix 2. The ones below cover theirs and add house checks.

### External FAQ (first)

Questions customers and the press will ask, in language they understand.

- [ ] What is the price, all in, and what does it replace?
- [ ] How does it work?
- [ ] What do I need before I start, and who installs it?
- [ ] How do I get help or support, and what happens when it fails?
- [ ] Where can I buy it?
- [ ] Is it safe, and who is responsible for compliance in my facility? *(house)*
- [ ] What happens to my data? *(house)*
- [ ] What works with it at launch, and what does not? *(house)*

### Internal FAQ (second)

Questions senior leaders and every department (finance, marketing, support, operations, HR, legal) will ask after reading the release.

- [ ] What does the target customer use today, who are the competitors, and how is this better, faster, or cheaper?
- [ ] Market size: how many customers have the problem, how many will pay to solve it, how much, and how many can use the product. Each figure sourced, arithmetic shown.
- [ ] Per-unit economics: gross profit and contribution profit per unit, and what has to be true for them to hold.
- [ ] Upfront investment (people, technology, inventory, space), how the team manages that risk, and months or years to profitability.
- [ ] Pricing rationale, compared with the customer's total cost of ownership and their alternatives *(house)*.
- [ ] The hard problems to solve (business model, engineering, legal, UI), the hardest technical risk, and the evidence it is solved.
- [ ] New capabilities the company must build.
- [ ] Third-party relationships and technologies the product depends on, why each partner will commit, and what each has committed to by launch.
- [ ] Regulatory and legal issues.
- [ ] Why now, why us, why it does not already exist *(house)*.
- [ ] Each side of a platform: why it shows up first, how the cold start ends *(house)*.
- [ ] Who owns contributed data, who is paid for it, and how the people who generated it (crews, workers, users) are treated *(house)*.
- [ ] What must be true for the product to succeed, and the top three reasons it will not.
- [ ] Every answer answers the question asked, with numbers that match the press release *(house)*.
