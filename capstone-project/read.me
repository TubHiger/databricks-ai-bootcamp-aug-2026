# Recall Radar — Agent Demo Transcript

The following is a live conversation with the Recall Radar agent (Databricks
Agent Bricks, in the AI Playground) using the MCP server's tools. It shows the
agent choosing tools per the system prompt, calling them, and answering from
the tool outputs — including read and write actions.

---

## Q1 — Semantic search (READ: search_recalls)

**User:** Are there any recalls involving undeclared peanuts or tree nuts?

**Agent → tool call:** `search_recalls({"query": "undeclared peanuts or tree nuts"})`

**Tool output (top results):**
- [Class I / High] Minnie Marie Bakers dba Awrey's Bakery — "Products may
  contain undeclared tree nuts (walnuts)... risk of serious or life-threatening
  allergic reaction." (similarity 0.699)
- [Class II / Medium] Better Business...Better Foods — "Contains undeclared
  almonds & undeclared sesame." (0.693)
- [Class II / Medium] Queen Bee Gardens — "Products may potentially contain...
  Pecans, Almonds, Coconut, Macadamia Nuts, & Walnuts." (0.686)
- [Class I / High] Farrell Farms — "Undeclared allergen: Milk." (0.673)

**Agent answer:** Reported the recalls, led with severity (High/Medium), and
added the disclaimer to verify with the manufacturer or the FDA.

---

## Q2 — Register products (WRITE: add_product)

**User:** Add peanut butter by Jif and a Honda Civic to my watchlist called 'aika'.

**Agent → tool calls:**
- `add_product({"label":"aika","kind":"food","name":"peanut butter","brand":"Jif"})`
  → `{"watchlist":"aika","added":{...}}`
- `add_product({"label":"aika","kind":"vehicle","name":"Civic","brand":"Honda"})`
  → `{"watchlist":"aika","added":{...}}`

Note: the agent correctly inferred `kind: food` for the peanut butter and
`kind: vehicle` for the Civic from natural language.

**Agent answer:** Confirmed both products were added to watchlist 'aika'.

---

## Q3 — Monitoring action (READ + WRITE: check_watchlist)

**User:** Check my watchlist 'aika' for any recalls.

**Agent → tool call:** `check_watchlist({"label":"aika"})`

**Tool output:** `alerts_created: 2`
- peanut butter → matched Quaker Manufacturing, LLC — "Product tested positive
  for Salmonella." severity **High**, match_confidence 0.718, action: "Class I
  recall (most serious). Stop using immediately and contact the firm."
- Civic → matched G.O. Fresh (cantaloupe/Salmonella) — severity High,
  match_confidence **0.516**.

**Agent answer:** Reported both alerts with severity and recommended actions —
and, notably, flagged the Civic match as **low-confidence / likely a false
positive** ("the match confidence is relatively low (0.5161)... this should be
verified"), rather than falsely alarming the user. This reflects the system
prompt's guardrail against overstating matches. (The Civic has no legitimate
match because the MVP ingests food recalls only.)

---

## Q4 — Retrieve stored alerts (READ: list_alerts)

**User:** Show me the alerts on my watchlist 'aika'.

**Agent → tool call:** `list_alerts({"label":"aika"})`

**Tool output:** the 2 alerts created in Q3, with severity, firm, reason, and
recommended action — proving the writes persisted to Lakebase.

---

## What this demonstrates

- The agent selects the correct tool per the system prompt's routing rules.
- **Read** (search_recalls, list_alerts) and **write** (add_product,
  check_watchlist → creates alerts) actions both work against Lakebase.
- Severity is derived from the FDA classification and surfaced in every answer.
- Guardrails hold: the agent never invents recalls, adds the FDA/manufacturer
  disclaimer, and honestly flags low-confidence matches instead of overstating.
