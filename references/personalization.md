# AI Personalization Pipeline

## Goal

For every contact, before composing their email, research the person and their dealership to fill the template slots with genuinely relevant, personal content.

## Research Process

### Step 1: Extract Base Data from DB

```sql
SELECT first_name, last_name, email, role, prospect_dealerships.name AS dealership,
       prospect_dealerships.brand, prospect_dealerships.city, prospect_dealerships.state
FROM prospect_dealership_contacts c
JOIN prospect_dealerships d ON c.prospect_dealership_id = d.id
WHERE c.id = {contact_id};
```

### Step 2: Web Research

Run 2-3 searches per contact:

1. **Dealership news:** `"{dealership_name}" "{brand}" "{city}" news` — Look for expansions, awards, new models, events, community involvement
2. **Brand-specific challenges:** `"{brand}" dealership challenges 2025 2026` — Industry context relevant to their franchise
3. **LinkedIn presence:** `site:linkedin.com "{first_name} {last_name}" {dealership}` — Recent posts, activity, shared content

### Step 3: Extract Personalization Hooks

From search results, identify:

| Hook Type | Use In | Example |
|-----------|--------|---------|
| Recent dealership news | Email 1 opener | "Saw {dealership} just expanded your service department — that's a big move." |
| Brand-specific challenge | Email 1 or 2 | "A lot of {brand} GMs I talk to are trying to figure out EV service integration right now." |
| Market context | Email 1 or 2 | "Being the only {brand} store in {city} comes with its own set of dynamics." |
| Comparable outcome | Email 3 | "Worked with a {similar_size} {brand} store that was dealing with the same thing." |
| Regional trend | Any email | "The {region} market has been particularly interesting this quarter." |

### Step 4: Fill Templates

Feed research hooks into the week's template. The AI fills each `{slot}` with the most relevant hook found.

### Step 5: Fallback

If research returns nothing useful, use generic-but-natural hooks:
- "Saw your dealership's online presence — impressive reputation."
- "The {brand} space has been evolving fast lately."
- "Always interesting to connect with {city}-area dealers."

### Step 6: Humanizer Pass

Mandatory — run the final composed email through humanizer rules before sending. Strip AI patterns, add natural variation, ensure conversational tone.

## Tooling

Use `web_search` for dealership/brand research. Use `browser` or `web_fetch` for LinkedIn if needed. Run research in parallel for batches to avoid slowing the daily send.
