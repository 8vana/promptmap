# Implementation Plan: Radial E2E Attack

## Summary

- `attack_id`: `radial_e2e`
- `paper_title`: Analyzing the Inherent Response Tendency of LLMs: Real-World Instructions-Driven Jailbreak
- `paper_url`: https://arxiv.org/abs/2312.04127
- `family`: `single_turn`
- `target_modes`: api, stateless
- `required_capabilities`: scorer_llm
- `supports_benchmark_recommendation`: `false`

RADIAL is an automatic jailbreak attack method that bypasses LLM safety mechanisms by analyzing inherent response tendencies and strategically placing real-world instructions around malicious content to amplify affirmation response generation.

## Algorithm Steps

### construct_responses. Construct Affirmation and Rejection Responses

Create 20 general affirmation responses and 20 general rejection responses that are not specific to any particular instruction

- `status`: `supported`
- `evidence_refs`: paper:section:3_2, paper:appendix_ref:a

### collect_instructions. Collect Real-World Instructions

Gather 30,000 real-world English instructions from alpaca official repository

- `status`: `supported`
- `evidence_refs`: paper:section:3_2, paper:footnote:1

### calculate_tendencies. Calculate Response Tendencies

For each real-world instruction, calculate affirmation tendency (Ta) and rejection tendency (Tr) using generation probabilities

- `status`: `supported`
- `evidence_refs`: paper:section:3_2, paper:formula:3_2

### score_instructions. Score and Rank Instructions

Calculate overall score for each instruction as Score = Ta - Tr and rank instructions by this score

- `status`: `supported`
- `evidence_refs`: paper:section:3_2, paper:formula:3_2

### filter_instructions. Filter Out Text Manipulation Instructions

Remove instructions that involve text manipulation (translation, rewriting) as they interfere with malicious instruction processing

- `status`: `supported`
- `evidence_refs`: paper:section:3_3

### splice_instructions. Splice Instructions Around Malicious Content

Select top-ranked real-world instructions and strategically place them around malicious instruction, with malicious instruction at the end

- `status`: `supported`
- `evidence_refs`: paper:section:3_3

## Prompt Fragments

### affirmation_response_example

```text
Sure, here's the information.
```
Evidence: paper:section:3_2

### rejection_response_example

```text
Sorry, I am unable to provide the information
```
Evidence: paper:section:3_2

## Ambiguities

- Planner MVP generated this draft heuristically; validate the attack flow against the paper.
- Default parameters are provisional unless the paper states them explicitly.
- Exact construction methodology for the 20 affirmation and 20 rejection responses not fully specified beyond examples
- Specific filtering criteria for text manipulation instructions not completely detailed
- Exact selection methodology for choosing which top-ranked instructions to use in splicing
- Complete prompt template structure not provided in paper excerpt
- Cross-language adaptation methodology for Chinese malicious instructions mentioned but not detailed in excerpt
- Benchmark recommendation was normalized to false in Phase A pending explicit human review.

## Evidence

### Paper Evidence

- `paper:title:1` `paper`
  Section: title
  Locator: top
  Quote: Analyzing the Inherent Response Tendency of LLMs: Real-World Instructions-Driven Jailbreak
  Interpretation: Paper title extracted from the first heading.
- `paper:section:abstract` `paper`
  Section: Abstract
  Locator: heading:Abstract
  Quote: Extensive work has been devoted to improving the safety mechanism of Large Language Models (LLMs). However, LLMs still tend to generate harmful responses when faced with malicious instructions, a phenomenon referred to as 'Jailbreak Attack'. In our research, we introduce a novel automatic jailbreak method RADIAL , whic
  Interpretation: Section excerpt captured during normalization.
- `paper:section:3_1` `paper`
  Section: 3.1 Overall
  Locator: heading:3.1 Overall
  Quote: Recent work (Zhao et al., 2024; Wei et al., 2023) indicated that the main goal of a successful jailbreak attack is to induce LLMs to generate affirmation responses rather than rejection responses. Therefore, our method attempts to create a condition within the prompt conducive to affirmation responses. In our work, we 
  Interpretation: Section excerpt captured during normalization.
- `paper:section:3_2` `paper`
  Section: 3.2 Inherent Response Tendency Analysis
  Locator: heading:3.2 Inherent Response Tendency Analysis
  Quote: As shown on the left side of Fig. 2, to initiate this analysis, we constructed 20 affirmation responses and 20 rejection responses, which are designed to be general and not specific to any particular instruction. For instance, a representative affirmation response takes the form of 'Sure, here's the information.' while
  Interpretation: Section excerpt captured during normalization.
- `paper:section:3_3` `paper`
  Section: 3.3 Real-World Instructions-Driven Jailbreak
  Locator: heading:3.3 Real-World Instructions-Driven Jailbreak
  Quote: As shown on the right side of Fig. 2, we perform real-world instructions-driven jailbreak. Based on the above instruction ranking, we select real-world instructions from the top that can inherently induce the LLMs to generate affirmation responses, thereby creating a condition within the prompt conducive to affirmation
  Interpretation: Section excerpt captured during normalization.
- `paper:section:4_1` `paper`
  Section: 4.1 Preliminary
  Locator: heading:4.1 Preliminary
  Quote: Before presenting the experiment results, we introduce our selected evaluation metrics, test data, advanced LLMs, and comparison baselines used in our experiments. Evaluation metrics. Consistent with previous work (Zou et al., 2023), We consider a jailbreak attack successful when the responses generated by LLMs contain
  Interpretation: Section excerpt captured during normalization.
- `paper:section:1` `paper`
  Section: 1 Introduction
  Locator: heading:1 Introduction
  Quote: Large Language Models (LLMs) (OpenAI, 2023; Touvron et al., 2023; Baichuan, 2023; Du et al., 2022b) exhibit great potential across fields, yet a significant hurdle to broader application lies in ensuring the harmlessness of their responses (Liu et al., 2023b). Substantial efforts have been dedicated to addressing this 
  Interpretation: Section excerpt captured during normalization.
- `paper:figure:1` `paper`
  Section: Figure 1
  Locator: figure:1
  Quote: Figure 1: Illustration of jailbreak methods. Manualdesigned methods typically demand substantial effort and face challenges in adaptability across LLMs. The automatic searched suffix lacks meaningful semantics, which can be easily detected by PPL algorithms. In comparison, our RADIAL method is an automatic process that
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:2` `paper`
  Section: Figure 2
  Locator: figure:2
  Quote: Figure 2: Overall framework of RADIAL method.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:appendix_ref:a` `paper`
  Section: Appendix A reference
  Locator: appendix-ref:A
  Quote: As shown on the left side of Fig. 2, to initiate this analysis, we constructed 20 affirmation responses and 20 rejection responses, which are designed to be general and not specific to any particular instruction. For instance, a representative affirmation response takes the form of 'Sure, here's the information.' while
  Interpretation: Inline appendix reference captured from paper body.
- `paper:footnote:1` `paper`
  Section: Footnote 1
  Locator: footnote:1
  Quote: 1 https://github.com/tloen/alpaca-lora
  Interpretation: Footnote line extracted from normalized markdown.
- `paper:appendix_ref:b` `paper`
  Section: Appendix B reference
  Locator: appendix-ref:B
  Quote: The other evaluation metric (Zhao et al., 2024) relies on the GPT-4 2 to analyze the semantics of responses. In App. B, we provide the details of the GPT-4 evaluation process and evaluate 6 sets of experimental results from our work to measure the performance of the two evaluation metrics. We observe that compared to t
  Interpretation: Inline appendix reference captured from paper body.
- `paper:footnote:2` `paper`
  Section: Footnote 2
  Locator: footnote:2
  Quote: 2 In our work, we use the GPT-4 API interface from November 1 to November 15, 2023
  Interpretation: Footnote line extracted from normalized markdown.
- `paper:appendix_ref:c` `paper`
  Section: Appendix C reference
  Locator: appendix-ref:C
  Quote: Comparison baselines. In our work, we explore both manual-designed and automatic searched methods as our comparison baselines. Examples for all attack prompts in our baseline can be found in App. C. For the manual-designed method, we first selected the Comp. method introduced in (Wei et al., 2023), which involves execu
  Interpretation: Inline appendix reference captured from paper body.
- `paper:footnote:3` `paper`
  Section: Footnote 3
  Locator: footnote:3
  Quote: 3 https://opencompass.org.cn/
  Interpretation: Footnote line extracted from normalized markdown.
- `paper:footnote:4` `paper`
  Section: Footnote 4
  Locator: footnote:4
  Quote: 4 https://www.jailbreakchat.com/
  Interpretation: Footnote line extracted from normalized markdown.
- `paper:footnote:5` `paper`
  Section: Footnote 5
  Locator: footnote:5
  Quote: 5 https://github.com/llm-attacks/llm-attacks
  Interpretation: Footnote line extracted from normalized markdown.
- `paper:figure:3` `paper`
  Section: Figure 3
  Locator: figure:3
  Quote: Figure 3: Distribution of the inherent response tendency scores of three advanced LLMs. The horizontal axis represents the score, and the vertical axis represents the number of real-world instructions.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:4` `paper`
  Section: Figure 4
  Locator: figure:4
  Quote: Figure 4: ASR(%) evaluated by GPT-4 are reported. In {k}\_{pos} on the horizontal axis, 'k' represents the number of selected real-world instructions, and 'pos' represents the position of the malicious instruction in the prompt. Moreover, when attacking each test sample, the term 'Top' denotes the selection of k instru
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:5` `paper`
  Section: Figure 5
  Locator: figure:5
  Quote: Figure 5: A case study of asking the follow-up question.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:6` `paper`
  Section: Figure 6
  Locator: figure:6
  Quote: Figure 6: ASR(%) evaluated by GPT-4 are reported. {k}\_{pos} has the same meaning as Fig.4.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:7` `paper`
  Section: Figure 7
  Locator: figure:7
  Quote: Figure 7: A real case under the Evil method to explain why GPT-4 evaluation is more accurate.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:8` `paper`
  Section: Figure 8
  Locator: figure:8
  Quote: Figure 8: Illustration of GPT-4 evaluation.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:9` `paper`
  Section: Figure 9
  Locator: figure:9
  Quote: Figure 9: The consistency of GPT-4 and KWM evaluations with human evaluation. 'green' represents cases that remain consistent and 'yellow' represents cases that remain inconsistent. 2\_end and 4\_end represent two experiment settings, which are detailed in the caption of Fig. 4.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:figure:10` `paper`
  Section: Figure 10
  Locator: figure:10
  Quote: Figure 10: Examples for all attack prompts in our baseline.
  Interpretation: Figure caption extracted from normalized markdown.
- `paper:formula:3_2` `paper`
  Section: 3.2 formulas
  Locator: section:3.2 formulas
  Quote: As shown on the left side of Fig. 2, to initiate this analysis, we constructed 20 affirmation responses and 20 rejection responses, which are designed to be general and not specific to any particular instruction. For instance, a representative affirmation response takes the form of 'Sure, here's the information.' while
  Interpretation: Detected 7 formula placeholder blocks in the normalized paper.

### Repo Evidence

No evidence recorded.

### Operator Notes

No evidence recorded.
