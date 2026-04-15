# Document Intelligence — Findings and Analysis

This document records the results of systematic testing across two document extraction backends: **Azure Document Intelligence** (a managed cloud service built on trained models) and **Claude Vision** (a general-purpose multimodal LLM accessed via the Anthropic API). The goal was not to pick a winner but to characterise each backend on its own terms — what it does well, where it breaks — and to propose an architecture that uses each where it is genuinely strongest.

---

## 1. Context

Document extraction is a deceptively hard problem because two different subtasks are stacked on top of each other:

1. **Perception** — reading text, numbers, tables, and visual structure from an image or PDF at the character level.
2. **Semantics** — understanding what a field *means* ("Total Due" vs "Subtotal" vs "Amount Paid") so downstream systems can reason about it consistently across documents.

Azure and Claude take fundamentally different approaches. Azure is built around trained models that recognise specific document types, with a fallback general-purpose layout extractor. Claude is a prompt-driven generalist that extracts whatever you describe in the prompt, with no prior training on any specific document format. Each approach has a distinct shape of strengths and weaknesses that only becomes visible when you put the same documents through both.

---

## 2. Methodology

Testing was performed against a FastAPI service exposing two endpoints — `/extract/azure` and `/extract/claude` — each with a model dropdown. Documents were uploaded through the Swagger UI and results were saved to JSON files for inspection.

**Documents tested:**

- Vodafone phone bill (baseline document, used for multiple runs)
- Phone bill with rearranged layout (same semantic content, different visual arrangement)
- Electricity and gas bills from the same provider (1st Energy)
- A payslip with a table-heavy layout
- An engineering drawing (T-slot bolt) — Azure tested, Claude pending

**Extractors tested:**

- Azure DI with `prebuilt-layout`, `prebuilt-invoice`, `prebuilt-read`
- Claude Vision with Opus 4.6, Sonnet 4.6, and Haiku 4.5

**What was measured:**

- Field coverage — how many fields each backend extracted
- Field name consistency — did the same semantic field get the same name across runs and across similar documents?
- Structural placement — did data end up in `fields`, `tables`, or `pages`?
- OCR accuracy on long alphanumeric identifiers (MIRN, Centrepay CRN, meter numbers) — character-level correctness
- Cost per document (from the Anthropic console for Claude; Azure is priced per page)

**What was *not* measured rigorously:**

- Engineering drawings through Claude Vision (pending)
- Token-level cost capture inside the extractor's response metadata (a known gap in the code today)
- Large-volume stability (hundreds of documents)

---

## 3. Azure Document Intelligence

### 3.1 How it works

Azure offers multiple prebuilt models that share an API shape but differ dramatically in behaviour:

- **`prebuilt-layout`** — general-purpose extractor. Reads text, detects tables, infers key-value pairs from visual layout. No fixed schema; field names come from the document's own labels.
- **`prebuilt-invoice`**, **`prebuilt-receipt`**, **`prebuilt-tax-document`**, etc. — document-type-specific models. Each returns a **fixed output schema** — always the same field names in the same shape — regardless of which vendor's invoice you give it.
- **`prebuilt-read`** — pure OCR. Returns text and bounding boxes. No structure, no key-value inference.

This split is the key to understanding Azure's behaviour: the prebuilt-specific models do semantic normalisation for you; `prebuilt-layout` does not.

### 3.2 Strengths

**Deterministic output.** Running the same document through the same Azure model multiple times produces byte-identical JSON. This is a genuine architectural advantage — regression-testing is trivial, caching is safe, and downstream code can compare outputs directly.

**Character-level OCR accuracy.** Azure's OCR is trained specifically on character recognition. Long alphanumeric identifiers (account numbers, MIRNs, Centrepay CRNs, meter numbers) come out correctly. This is exactly where vision LLMs struggle most.

**Layout invariance in prebuilt models.** When the same Vodafone phone bill was uploaded in two visually different layouts — the same semantic content rearranged on the page — Azure's prebuilt models extracted the same fields with the same names and values in both cases. This is *semantic recognition, not template matching*. For documents that fit a trained type, Azure understands what a "due date" means regardless of where it appears.

**Fixed-schema normalisation in prebuilt-specific models.** `prebuilt-invoice` always returns `VendorName`, `InvoiceDate`, `DueDate`, `SubTotal`, `TotalTax`, `InvoiceTotal`, and a structured `Items` array. If the field is in the document, it comes out with that exact name. If it's missing, the field is null. This is *internal normalisation* — a downstream system can hard-code references to `InvoiceTotal` and trust that every invoice extraction will have that field in that exact shape. You do not need an LLM normalisation layer for document types Azure has a prebuilt for.

**Template-family consistency within a provider.** Two electricity bills from the same provider produced the same field names and structural organisation. A gas bill and an electricity bill from the same provider shared identical field names for the common data (account number, customer address, billing period, amount due) and differed only where the documents genuinely differed (electricity vs gas-specific fields). This is the correct behaviour — the documents really do describe different services.

**Cost-effective at scale.** `prebuilt-layout` is roughly $0.01 per page. For documents where Azure handles the whole job (most business documents — invoices, receipts, bills), it is hard to beat.

### 3.3 Weaknesses

**Structure-dependent output placement.** A payslip with a table-heavy layout — earnings, deductions, and YTD totals all formatted as tables — produced an extraction where most of the important data ended up in the `tables` array, not in `fields`. Azure correctly identifies tables as tables, but downstream code that reads `result.fields["gross_pay"]` will fail because the "gross pay" value is buried in `result.tables[0].cells[4][2]`. Code that processes payslips must know to look in the tables; code that processes invoices can use the fields directly. Same extractor, two completely different integration patterns.

**`prebuilt-layout` has no fixed schema.** Field names come from whatever labels appear on the document. Two invoices from different vendors can have different field names if the vendors use different wording. This is where normalisation becomes necessary.

**No prebuilt models for novel document types.** Engineering drawings, technical datasheets, specialised industry forms — Azure has no prebuilt-specific model. You fall back to `prebuilt-layout`, which reads the text correctly but does not understand the document semantically. For an engineering drawing, Azure extracted dimensions and annotations as layout tables but had no concept of what a "revision history", "bill of materials", or "projection standard" means.

**No semantic reasoning.** Azure extracts what it can see. It does not infer document type, it does not classify, it does not reason about ambiguous fields. It is a perception engine, not an understanding engine.

### 3.4 What Azure is best for

- Invoices, receipts, tax documents — **always use a prebuilt-specific model**. The internal normalisation is effectively free.
- Utility bills, phone bills — `prebuilt-layout` works well, but peripheral field names vary across providers; normalisation layer recommended.
- Any production pipeline where byte-deterministic output is a hard requirement.
- Any field that requires character-level OCR accuracy — long alphanumeric IDs.

---

## 4. Claude Vision

### 4.1 How it works

Claude Vision is a general-purpose multimodal LLM with image-input capability. You send one or more images in a single API call, along with a text prompt describing what to extract and in what JSON shape. Claude reads the image, classifies the document type, and returns structured JSON. There is no prior training on any document format — all the schema logic lives in the prompt.

The current implementation sends all pages of a PDF in a single API call (as multiple images attached to one user message) so Claude can produce a unified multi-page extraction without cross-page duplication or naming drift. The prompt defines nine document-type categories and a canonical snake_case field schema per type, with strict rules against placeholder values like "N/A" or "Not visible".

### 4.2 Strengths

**Prompt-driven schema control.** There is no fixed output schema imposed by the model — whatever you describe in the prompt is what comes back. This is the structural opposite of Azure and is the single biggest advantage: the schema is a first-class engineering artefact, not a side-effect of model training. Switching from snake_case to camelCase, adding a new field, restructuring tables — all prompt edits, no retraining, no new model selection.

**Universal document handling.** The same prompt and the same code path work on invoices, payslips, utility bills, engineering drawings, and any novel document type. Claude classifies the document first, then extracts into the canonical schema for that type. This is the only practical way to handle the long tail of document types for which no prebuilt model exists.

**Semantic reasoning about ambiguous fields.** When a field could reasonably be labelled two ways, Claude picks sensibly most of the time — for example, choosing "MJ" (the billed unit) over "m³" (the raw meter unit) as the `usage_unit` on a gas bill. It does not always get this right, but it can reason about the document's intent, where Azure can only extract visible text.

**Document type classification built in.** Every extraction includes `document_type` and `document_type_confidence` in metadata. This is exactly what a routing system needs upstream of extraction, for free.

**Cost at Haiku tier is competitive.** Haiku 4.5 runs at roughly $0.01 per page on two-page documents — matching Azure's `prebuilt-layout` pricing. At Sonnet 4.6 the per-page cost is roughly 2.5× Haiku; at Opus 4.6 it is roughly 4× Haiku. **Vision image tokens are priced the same across all three tiers** because the image encoder is shared, so only the output generation scales with model tier, which is why the cost gap between tiers is much smaller than the published per-token pricing would suggest.

### 4.3 Weaknesses

Claude Vision's weaknesses cluster into two categories: **OCR fidelity** (which improves with tier) and **schema stability** (which does not).

#### 4.3.1 OCR accuracy is tier-dependent

On a 1st Energy gas bill, three long alphanumeric identifiers (MIRN, Centrepay CRN, meter number) were tracked across model tiers:

| Field | Haiku 4.5 | Sonnet 4.6 | Opus 4.6 (3 runs) |
|---|---|---|---|
| MIRN (11 digits) | truncated to 10 digits, different digit missing each run | correct | **correct, all 3 runs** |
| Centrepay CRN | `SS51I7312V` or `555117312V` | `55S117312V` (one misread) | **`555117312V` correct, all 3 runs** |
| Meter number | `4998OD/1` | `4998OD/1` | `4998OD/1` ← confirmed correct |

The pattern is clear: Haiku misreads long identifiers catastrophically (dropping digits, confusing similar glyphs like 5↔S, 7↔I, 0↔O). Sonnet improves substantially but still occasionally misreads one character. **Opus was character-deterministic across three consecutive runs** on this document.

This distinction matters because it is not hallucination — Claude is not inventing values. It is OCR error: the model is looking at pixels and misreading individual characters, and the error rate drops with model tier but does not hit zero below Opus. Long alphanumeric identifiers without semantic meaning (no linguistic prior for the model to lean on) are the single worst case for any vision LLM.

#### 4.3.2 Schema stability does NOT improve with tier

Three consecutive Opus runs on the same 1st Energy bill produced **three different schemas**. The core canonical fields (~22 fields) were identical across all three runs. Everything beyond that drifted — not noise around a mean, but genuinely different structural decisions:

**The consistency gradient across Opus runs:**

| Tier | Content | Opus stability |
|---|---|---|
| 1 | Canonical fields (names matching prompt schema + values) | Deterministic across 3 runs |
| 2 | Peripheral field names (fields Claude invents from document labels) | Drifts — same concept gets different snake_case names each run |
| 3 | OCR of long identifiers | Deterministic at Opus, broken at lower tiers |
| 4 | Content-choice when multiple answers exist (MJ vs m³) | Stable at Opus |
| 5 | Schema structure — whether a concept is one field or split into two, whether it lives in fields or a table | Drifts — fields merge, split, or move between runs |
| 6 | Information completeness — whether a given piece of data is extracted at all | Drifts — Opus Run 3 dropped the gas network entirely, which Runs 1 and 2 captured |

Concrete examples from three Opus runs of the same document:

- **Name drift (Tier 2):** `gst_amount` (R1, R2) → `gst_charge` (R3). `faults_emergencies_phone` (R1, R2) → `provider_faults_phone` (R3). Six fields exhibited naming drift across three runs.
- **Field splitting (Tier 5):** `guaranteed_discount` = "$4.49" (R1, R2) → split into `guaranteed_discount_percentage` = "7%" + `guaranteed_discount_amount` = "$4.49" (R3).
- **Table splitting (Tier 5):** the charges calculation was a single table in R1 and R2, split into a line-items table plus a totals-and-discounts table in R3.
- **Table disappearance (Tier 5):** the Payment Methods table was extracted in R1 but not in R2 or R3.
- **Information loss (Tier 6):** `gas_network` = "Multinet Gas Network" was present in R1 and R2 but entirely absent from R3. The data is in the document; Claude just decided not to extract it this run.
- **Novel additions:** R3 added `currency` = "AUD", which R1 and R2 did not produce.

**The practical consequence:** you cannot build downstream code that assumes a given peripheral field will be present, or will have a particular name, or will live in `fields` rather than `tables`. The canonical schema is stable; everything else is a probability distribution.

#### 4.3.3 Chart and diagram content

The historical peak usage chart on page 2 of the 1st Energy bill was extracted as a table **only once** (when page 2 was tested in isolation) across all Haiku, Sonnet, and Opus runs. When both pages are sent together, Claude always prioritises the charges/summary tables and drops the visual chart. This is worth noting for any document where visual content matters — bar charts, usage histograms, revision tables with visual formatting.

### 4.4 What Claude Vision is best for

- Novel document types where Azure has no prebuilt model (engineering drawings, specialised industry forms).
- Any task where document-type classification is needed upfront.
- Documents where semantic field naming (canonical snake_case via prompt) is more valuable than character-level precision.
- Prototype/exploration phases where a schema is still being designed — the prompt is iterable in ways trained models are not.

---

## 5. Side-by-side comparison

| Dimension | Azure Document Intelligence | Claude Vision |
|---|---|---|
| **Determinism across runs** | Byte-identical output | Canonical fields stable; peripheral fields, tables, and structure drift even at Opus |
| **OCR on long alphanumeric IDs** | Reliable at every model | Unreliable at Haiku/Sonnet, reliable at Opus on tested doc |
| **Schema stability** | Fixed for prebuilt-specific models; document-driven for `prebuilt-layout` | Driven entirely by the prompt; canonical part stable, invented part unstable |
| **Document-type classification** | Implicit (you choose the model) | Built in (returned on every call) |
| **Handles novel document types** | Falls back to `prebuilt-layout`, no semantic understanding | Yes — prompt-driven, universal |
| **Handles table-heavy layouts** | Extracts tables correctly but leaves fields empty | Flattens tables into fields when prompt asks for canonical names |
| **Chart / diagram content** | Not extracted as structured data | Occasionally extracted as a table, inconsistent |
| **Layout invariance (same content, different arrangement)** | Strong for prebuilt-specific models | Strong — prompt schema is independent of layout |
| **Per-page cost** | ~$0.01 for `prebuilt-layout` | ~$0.01 Haiku, ~$0.025 Sonnet, ~$0.04 Opus |
| **Vendor lock-in** | Azure-specific | Anthropic-specific |
| **Schema iteration speed** | Slow — add a new field requires a new model or post-processing | Instant — edit the prompt |

**Azure wins on:** determinism, OCR accuracy, cost at scale, and document types where a prebuilt-specific model exists.

**Claude Vision wins on:** flexibility, novel document types, semantic reasoning, and built-in classification.

**Both fail in the same place:** neither handles chart content or visual diagrams reliably. Azure sees them as layout blocks without meaning; Claude drops them in favour of tabular content.

---

## 6. Architectural recommendation

The headline finding is that **neither backend alone is sufficient for a production pipeline** that needs both character-level accuracy and schema stability across document types. The right architecture uses each backend for what it does well.

### 6.1 The recommended hybrid

For document types that Azure supports (invoices, receipts, bills, payslips, tax documents, bank statements):

1. **Azure `prebuilt-layout` (or `prebuilt-invoice` / equivalent) does the perception layer.** It provides character-accurate OCR and a deterministic field/table structure. This solves the OCR accuracy problem and the schema-stability problem in one step, because Azure's output for a given document is byte-identical across runs.
2. **Claude (Haiku tier) does the normalisation layer.** The prompt provides the canonical schema — "given this Azure JSON, output these exact field names if the data is present, omit them otherwise." The LLM is no longer reading pixels, so image tokens drop out of the cost. The LLM is no longer inventing schema, so the naming and structural drift (Tiers 2, 5, 6 in section 4.3.2) disappear — the prompt pins the schema; the LLM just fills slots.
3. **Result:** deterministic canonical output, character-accurate values, at roughly the cost of Azure alone.

For document types Azure cannot handle well (engineering drawings, novel formats, documents dominated by visual content):

1. **Claude Vision at Sonnet or Opus tier** is the only practical option. Accept the schema instability as the cost of handling the long tail, and rely on the prompt's canonical schema for the fields that matter most. Use Opus for documents with important long alphanumeric identifiers; use Sonnet where OCR precision is less critical.

### 6.2 Per-document-type routing

| Document type | Recommended backend | Why |
|---|---|---|
| Invoices, receipts, tax documents | Azure prebuilt-specific model | Built-in schema normalisation, lowest cost, deterministic |
| Utility bills, phone bills | Azure `prebuilt-layout` + Haiku normaliser | Character accuracy from Azure; canonical names from Claude |
| Payslips | Azure `prebuilt-layout` + Haiku normaliser | Most data is in tables; normaliser flattens to canonical fields |
| Bank statements | Azure `prebuilt-layout` + Haiku normaliser | Transaction tables are Azure's strength; schema normalisation is Claude's |
| Engineering drawings | Claude Vision (Opus or Sonnet) | No Azure prebuilt exists; layout extraction is insufficient |
| Unknown / novel document types | Claude Vision (tier depends on budget) | Only prompt-driven extraction can handle arbitrary formats |

### 6.3 Why not Claude Vision as a primary backend for everything

Three Opus runs on the same document produced three different schemas, and one of those runs silently dropped a piece of data that the other two extracted. For any downstream system that reads extracted fields by name, that is a correctness failure — not "slightly different output", but fields that *disappear between runs*. The fix is not "use Opus more carefully" — it is architectural. OCR is only reliable at Opus tier, but Opus is also the most expensive tier and still does not fix schema drift.

### 6.4 Why not Azure alone

Azure has no semantic reasoning and no prebuilt models for the long tail. For engineering drawings and similar documents, its output is text blocks without structure — sufficient as raw input to a downstream system, but not as a finished extraction. And even for document types Azure handles well, `prebuilt-layout` produces vendor-specific field names that need a normalisation layer before they are useful across providers.

---

## 7. Open questions and future work

**Engineering drawings through Claude Vision.** The T-slot bolt drawing was tested through Azure; Claude Vision has not yet been run on it. Expected outcome is that Claude performs substantially better because it can reason about visual features (dimensions, projection standards, revision tables), while Azure treats them as undifferentiated layout blocks. A formal comparison across multiple drawing formats (different companies, different standards) would be needed to draw firm conclusions.

**Token-level cost capture.** The Anthropic SDK returns `response.usage.input_tokens` and `response.usage.output_tokens` on every call. The current implementation in `doc_intel/extractors/claude_vision.py` does not capture this data, meaning cost figures in this document come from the Anthropic console rather than from extraction metadata. Adding usage capture to `ExtractionResult.metadata` would enable per-document cost reporting and empirical cost-per-document-type analysis.

**Implementing the normalisation layer.** The architectural case above has been made but not built. The next engineering step is a `ClaudeNormalizer` that takes Azure's output, applies the canonical per-type schema via a Haiku prompt, and emits the final unified schema. The cost, latency, and stability of this pipeline should then be measured against Claude-Vision-alone and Azure-alone baselines.

**Classification upstream of routing.** A routing system needs to know the document type before it picks a backend. Options include a lightweight Claude call (classification only, with a short prompt), a rules-based classifier on Azure `prebuilt-read` output, or a small trained classifier on embedded features.

**Haiku quality threshold for normalisation.** Haiku's cost parity with Azure makes it architecturally attractive for normalisation, but its reliability at the normalisation task specifically (taking structured JSON in, producing structured JSON out, no vision) has not been measured. Expected to be high because the vision failure mode is absent, but needs verification.

**Larger-scale consistency sampling.** The schema drift results are based on three Opus runs on one document. A meaningful statistical picture would require ~20 runs across several document types, so the frequency of each drift mode (name change, field disappearance, table split) can be quantified rather than just illustrated.

---

## 8. Summary

The "Azure vs Claude" framing is too coarse. Each backend has multiple modes of operation with different cost, consistency, and flexibility characteristics. Azure offers deterministic, character-accurate extraction with fixed schemas — ideal for document types it has prebuilt models for, but structurally limited for novel formats and for peripheral field naming. Claude Vision offers full prompt-driven schema control across any document type, but its schema is only stable for the canonical core — peripheral fields, tables, and even field presence drift across runs at every model tier, including Opus.

The most important empirical findings from this round of testing:

- **Azure is byte-deterministic; Claude is not, even at Opus.**
- **Claude Vision's OCR is tier-dependent**: Haiku misreads long identifiers, Sonnet is better but imperfect, Opus was deterministic across three runs on the tested document.
- **Claude Vision's schema drift is not tier-dependent**: it happens at Opus as readily as at Haiku. This is an LLM-level behaviour, not a tier ceiling.
- **The cost story is more nuanced than "Claude costs more"**: Haiku matches Azure's per-page pricing because vision image tokens are the same across tiers. Only output scales with tier.

The architectural takeaway is to use each backend for what it does well, not to choose between them. Azure provides the character-accurate perception and deterministic structure. Claude (at Haiku tier, operating on JSON rather than pixels) provides the canonical schema normalisation. For document types Azure cannot handle, Claude Vision at Opus or Sonnet is the fallback, accepting schema drift as the cost of handling the long tail.

The cost and quality data published here should be treated as a starting point for further measurement, not as a general-purpose ranking of the backends.
