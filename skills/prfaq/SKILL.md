---
name: prfaq
description: Line-by-line checklist for writing and reviewing an Amazon-style PR/FAQ (a future press release plus FAQ), including platform and marketplace launches. Use whenever the task drafts, edits, restructures, or reviews a PR/FAQ, a launch press release, its heading or subheading, or its FAQ, or asks how an Amazon executive would judge one.
---

# PR/FAQ

A PR/FAQ is a press release for a product that does not exist yet, written from its launch date, followed by the questions a customer and a decision maker will ask. The press release fits on one page. If it cannot make the hero customer want the product, the product changes before the document does.

Sources for the structure:

- Ian McAllister's 2012 Quora answer on Amazon's internal press releases, summarized with his section list by [Mequoda](https://www.mequoda.com/articles/audience-development/an-inspirational-press-release-template-from-amazon).
- Colin Bryar and Bill Carr, [Working Backwards PR/FAQ Instructions & Template](https://workingbackwards.com/resources/working-backwards-pr-faq/), and their book *Working Backwards* (St. Martin's Press, 2021).
- AWS, [Product Management at Amazon](https://aws.amazon.com/executive-insights/content/product-management-at-amazon/), which says the press release "must fit on a single page."

McAllister and Bryar and Carr give the same press release order: heading, subheading, summary, problem, solution, then quotes and getting started. Bryar and Carr group the spokesperson quote, the customer quote, getting started, and a link to the website as one block. McAllister orders them spokesperson quote, getting started, customer quote, then a separate closing and call to action, and this skill follows him. Neither template has a separate proof paragraph, partner quote, or price section. Each check below comes from one of these sources.

Use the checklist two ways. Authors tick it while drafting. Reviewers report each unmet item as a finding in the `unified-review` format (severity groups, inline diffs). The `logic` skill still applies to the argument, and CLAUDE.md's writing rules still apply to every sentence.

## Before drafting

- [ ] **Hero customer.** One precisely defined customer segment. Bryar and Carr: "If you think your product is for everyone, you are mistaken."
- [ ] **One PR/FAQ per side.** A product with two kinds of customer can need two PR/FAQs. Fulfillment by Amazon had one from the seller's side and one from the buyer's. For a marketplace, decide whether the supply side (creators, developers, sellers) needs its own.
- [ ] **The most important problem.** Of the problems the product could solve, the one that matters most to the hero, and one with enough customers willing to pay to make the market worth entering.
- [ ] **Today's alternatives.** What the hero uses now to deal with the problem, and why it falls short. There is always a current solution.
- [ ] **The one differentiator.** How the product is better, faster, or cheaper than those alternatives, in language the customer understands, with no corporate jargon (Bryar and Carr). If it solves the problem the way existing products do, go back to the drawing board.
- [ ] **Launch date.** A date the team expects to launch. Bryar and Carr: a rough estimate at first, the planned launch date by the final draft.

## Press release, line by line

Write the elements in this order. Each item names what the element must do, then what to check.

### 1. Heading

- [ ] Names the product so the target customer understands it.

### 2. Subheading

- [ ] One sentence. Both templates say so.
- [ ] Names the customer segment precisely and the benefit they gain.

### 3. Summary paragraph

- [ ] Opens with the city, the media outlet, and the launch date: "BERKELEY, Calif. (BUSINESS WIRE), November 14, 2028:" or the outlet's own dateline style.
- [ ] Summarizes the product and its benefits. McAllister: "Assume the reader will not read anything else."

### 4. Problem paragraph

- [ ] The problem(s) the product solves, from the customer's point of view.
- [ ] The problem(s) most important to the customer. Bryar and Carr: "Not all problems are created equal."
- [ ] Comes before the solution.

### 5. Solution paragraph(s)

- [ ] Describes the product in enough detail to show how it simply and directly solves the problem in element 4. More than one paragraph is fine for a complex product.
- [ ] Addresses the stated problem, not other needs. A laundry list of features that do not touch the problem gets cut.
- [ ] **Names today's alternatives.** Bryar and Carr: the solution paragraph "should include: 'Today, customers with this problem use x, y, or z products to meet their needs. Those products fall short of solving x problem(s). Our product addresses these unmet needs in the following ways.'" The solution paragraph contains a sentence of that form, naming the specific alternatives, how each falls short, and how the product addresses that gap. A draft that mentions competitors elsewhere, or only in the FAQ, fails this check.
- [ ] **Price, only as the differentiator.** A price appears in the release only where it shows the product is cheaper than today's alternatives, in this paragraph beside them. Bryar and Carr's model release states its car's price as part of what makes it "meaningfully better/faster/cheaper than the alternatives." Tiers, subscriptions, what is included, revenue splits, and how the price is set go in the External FAQ under "What is the price?"
- [ ] Clear and brief. Long, vague, or high-level descriptions fail.

### 6. Spokesperson quote

- [ ] One quote from the company's spokesperson.

### 7. How to get started

- [ ] Shows how easy it is to get started.

### 8. Customer quote

- [ ] One quote from a hypothetical customer describing how they experienced the benefit.

### 9. Closing and call to action

- [ ] Wraps up and points the reader to where to learn more and get started, with a link.
- [ ] No price-and-availability paragraph. Neither template has a price section, and Bryar and Carr make "What is the price?" the first External FAQ.

## Whole release

- [ ] Fits on one page.
- [ ] One hero, one segment.
- [ ] Two quotes: the spokesperson and the customer.
- [ ] No jargon the hero would not use: replace "catastrophic forgetting," "TCP," "pipeline," "ecosystem" with what they mean for the customer.
- [ ] Any price in the release sits in the solution paragraph and shows the differentiator (element 5). Pricing detail is in the External FAQ.
- [ ] Written for the customer. Bryar and Carr: while writing it, "You aren't focused on your competitors, current capabilities, P&L, business partners, or other considerations." This does not cancel element 5, which still names today's alternatives.

## FAQ

External questions come first, then internal ones (Bryar and Carr). AWS: "We don't include every possible question." Bryar and Carr list standard questions on the [Working Backwards page](https://workingbackwards.com/resources/working-backwards-pr-faq/), Appendix 2, and name others in its FAQ section. The questions below are theirs, in their order, plus the questions AWS names.

### External FAQ (first)

Questions customers and the press will ask, in language they understand.

- [ ] What is the price?
- [ ] How does it work?
- [ ] How do I install it?
- [ ] What is the warranty?
- [ ] What is the return policy?
- [ ] How do I get help or customer support?
- [ ] Where can I buy it?
- [ ] What happens when the product breaks? (AWS)
- [ ] Why would I choose this over another product? (AWS)
- [ ] Will my data be secure? (AWS)

### Internal FAQ (second)

Questions senior leaders and every department (finance, marketing, customer support, operations, HR) will ask after reading the release, and the challenging problems to solve, "whether technical, financial, legal, or operational" (Bryar and Carr).

- [ ] What products or solutions does the target customer use today to solve this problem?
- [ ] What problem(s) does this product solve for customers?
- [ ] How does it create value for customers: in what ways is it better, cheaper, and faster than the alternatives?
- [ ] Who are the current competitors?
- [ ] How large is the estimated demand, and what is the total addressable market? How many customers have this need, how many will pay to solve it and how much, and how many have the characteristics, capabilities, and constraints needed to use the product?
- [ ] What happens if a customer encounters x? How does the product deal with use case x?
- [ ] What challenging problems (business model, engineering, legal, UI) must be solved to enable the product?
- [ ] What new capabilities must the company establish to support it?
- [ ] What third-party relationships or dependencies does it need, and why will each partner be willing to partner (what is in it for them)? What third-party technologies must work for the product to work as promised?
- [ ] What regulatory or legal issues apply?
- [ ] What are the per-unit economics: expected gross profit and contribution profit per unit?
- [ ] How much upfront investment (people, technology, inventory, warehouse space) does it need, and how will the team manage that risk?
- [ ] From the upfront investment and the per-unit economics, how many months or years until it is profitable?
- [ ] What assumptions need to be true for the product to succeed?
- [ ] What are the top three reasons it will not succeed?
- [ ] Might it cannibalize other products? (AWS)
- [ ] Do we have the resources to make this work? (AWS)
