# Business model (hypotheses and an illustrative calculator)

Status: **nothing in this file is measured.** It is arithmetic on stated assumptions plus two quoted industry
statistics, each with its limits. Read `docs/CLAIMS_AUDIT.md` first; this document adds no row to it that is
stronger than "unverified" or "illustrative".

## What we do NOT claim

- No ARR, revenue, pilots, customers or letters of intent. None exist.
- No prevented breaches and no prevented fraud. Every attack in this repo is a synthetic fixture.
- No TAM, SAM or market-share figure.
- The **$24,800 invoice is synthetic exposure** (a fictional vendor invoice used in the demo). It is never "saved",
  "recovered" or "prevented" money, and it must not appear in any ROI figure.
- No claim that a buyer would pay (CLAIMS_AUDIT: "Buyer would pay: unverified, no interviews done").
- The $2,500 per month price below is a placeholder to make the arithmetic concrete. It has not been tested with anyone.

## Productivity calculator (ILLUSTRATIVE, NOT MEASURED)

Run `python3 scripts/business_calc.py --sensitivity` (stdlib only; `--json` for machine output; every input is a flag).

```
time_value = cases_per_day * max(0, minutes_before - minutes_after) / 60 * workdays * hourly_cost
net        = time_value - monthly_price
annualised = 12 * net
```

| Input | Default | Meaning | Status |
|---|---:|---|---|
| cases_per_day | 30 | policy-relevant agent incidents an analyst team investigates per workday | ILLUSTRATIVE |
| minutes_before | 18 | investigation time per case without the tool | ILLUSTRATIVE |
| minutes_after | 7 | investigation time per case with the tool | ILLUSTRATIVE |
| workdays | 20 | workdays per month | ILLUSTRATIVE |
| hourly_cost | $85 | fully loaded cost per analyst hour | ILLUSTRATIVE |
| monthly_price | $2,500 | licence price | ILLUSTRATIVE |

With these defaults: 11 minutes saved per case, **$9,350 per month gross time value**, **$6,850 per month net**,
**$82,200 per year** (12 x net). Break-even is about 2.94 minutes saved per case at 30 cases/day. A team that saves less
than that, or has far lower volume, shows a negative net (see the table); the calculator reports negatives and never
clamps net to zero. `tests/test_business_calc.py` pins these numbers.

### Sensitivity: monthly NET in USD (price $2,500, 20 workdays, $85/h; ILLUSTRATIVE)

Rows are minutes saved per case, columns are cases per day.

| minutes saved per case \ cases per day | 10 | 20 | 30 | 50 | 100 |
|---|---:|---:|---:|---:|---:|
| 2 | -$1,933 | -$1,367 | -$800 | $333 | $3,167 |
| 5 | -$1,083 | $333 | $1,750 | $4,583 | $11,667 |
| 8 | -$233 | $2,033 | $4,300 | $8,833 | $20,167 |
| 11 | $617 | $3,733 | $6,850 | $13,083 | $28,667 |
| 15 | $1,750 | $6,000 | $10,250 | $18,750 | $40,000 |

**Real savings must be measured from observed investigation durations** (time-stamped investigations of the same
case mix by the same analysts, before and after, with enough cases to report an interval). Until then the numbers
above describe the formula, not the product. The 18 and 7 minute figures were chosen by us; nothing in this repo
measures how long a human takes to investigate an agent incident, with or without PHANTOMSHIFT.

## Industry context (quoted with limits; accessed 2026-10-25)

Both URLs were opened on 2026-10-25 with a fetch tool that returns a model-written summary of the page, not the raw
HTML. The figures below matched the operator brief; treat the exact wording as read through that summariser.

| Source | Figure as stated | Verified? | Limits |
|---|---|---|---|
| IBM, Cost of a Data Breach Report 2026, https://www.ibm.com/reports/data-breach | Global average breach cost **$4.99M** (page: 12% increase, record high). **$1.93M** cost savings "from extensive use of AI and automation in security" compared with organisations using none. | **Verified** (page opened; both numbers present) | The page states no methodology, sample size, period or outlier treatment (it names IBM with Ponemon Institute). "Extensive use" is not defined and the comparison does not say it controls for company size, sector or maturity, so it is an association, not evidence that automation causes lower cost. It is about breach cost generally, not about agent-policy tooling, and says nothing about PHANTOMSHIFT. |
| Cloud Security Alliance press release, 2026-04-21, https://cloudsecurityalliance.org/press-releases/2026/04/21/new-cloud-security-alliance-survey-reveals-82-of-enterprises-have-unknown-ai-agents-in-their-environments | **82%** of organisations have unknown AI agents in their IT infrastructure; **65%** had AI-agent-related incidents in the past 12 months. | **Verified** (page opened; both numbers present) | Survey commissioned by Token Security, a vendor in the space. 418 IT and security respondents, online, January 2026. Self-reported; "incident" and "unknown agent" are as the respondents understood them (the definitions were not seen); respondent selection and weighting not seen. Supports "the problem is reported as common", not a rate for any one company, and not that our policy approach fixes it. |

Use these only as context for why the problem might matter. Do not multiply them into a market size.

## Buyer and monetisation (HYPOTHESES, none validated)

- **Buyer hypothesis:** security engineering and AI-platform engineering teams that run tool-using agents with
  access to money, mail or network egress, and SOC leads who would have to investigate an agent incident. No interviews done.
- **Monetisation hypothesis:** an annual licence priced per monitored agent, or per test execution (counterfactual
  policy test run), with a self-hosted option because the whole stack is designed to run on-prem on a GB10-class box.
  Pricing, packaging and willingness to pay are all untested.
- **Value hypothesis:** the repair loop (attack found, three candidate policies replayed, one verified, human approves)
  shortens the time from detection to an approved policy change. Not measured: the live pipeline does not exist yet
  (PROGRESS.md), and the replay is policy-only, not counterfactual agent behaviour.

## How to turn this into evidence

1. Time 20-30 real or realistic incident investigations manually; record start and end timestamps.
2. Repeat with the tool on a comparable set; report median and spread, not only the mean.
3. Replace the six defaults with observed values (hourly cost from the buyer, not from us) and re-run the calculator.
4. Ask the buyer hypothesis question directly in interviews before quoting any price.
