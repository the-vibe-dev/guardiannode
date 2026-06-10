# Ollama Model Licenses

GuardianNode does **not** bundle model weights. Models are pulled by Ollama at install time from the model author's distribution. Each model has its own license that you must comply with.

The model presets GuardianNode recommends:

## Text classification models

| Tier | Model | License | License URL | Notes |
|---|---|---|---|---|
| Tiny | `llama3.2:1b` | Llama 3.2 Community License | https://www.llama.com/llama3_2/license/ | Acceptable use restrictions apply; non-commercial OK; ≥700M MAU triggers separate agreement |
| Small | `llama3.2:3b` | Llama 3.2 Community License | https://www.llama.com/llama3_2/license/ | Same as above |
| Medium | `qwen2.5:7b-instruct` | Apache-2.0 | https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/blob/main/LICENSE | Fully permissive |
| Medium-alt | `mistral:7b-instruct` | Apache-2.0 | https://mistral.ai/news/announcing-mistral-7b/ | Fully permissive |
| Large | `qwen2.5:14b-instruct` | Apache-2.0 | https://huggingface.co/Qwen/Qwen2.5-14B-Instruct/blob/main/LICENSE | Fully permissive |

## Vision classification models

| Tier | Model | License | License URL | Notes |
|---|---|---|---|---|
| Tiny | `moondream` | Apache-2.0 | https://huggingface.co/vikhyatk/moondream2 | Small, fast, CPU-runnable |
| Small | `llava-phi3:3.8b` | MIT (Phi-3) + LLaVA Apache-2.0 | https://huggingface.co/xtuner/llava-phi-3-mini-hf | Composite |
| Medium | `llava:7b` | LLaVA Apache-2.0 | https://github.com/haotian-liu/LLaVA/blob/main/LICENSE | Fully permissive |
| Large | `llama3.2-vision:11b` | Llama 3.2 Community License | https://www.llama.com/llama3_2/license/ | Same restrictions as text Llama models |

## Acceptable Use

The **Llama Acceptable Use Policy** (applies to all Llama-derived models) forbids using the model:
- To plan or attempt acts of violence
- For child sexual exploitation
- For misleading deceptive content

GuardianNode uses these models **defensively**, to flag content matching these abuse categories on behalf of a parent monitoring their own child's PC. This is consistent with the Llama AUP. However, you the deployer are responsible for ensuring your usage complies.

## Why no bundled weights

1. **License compliance** — bundling weights would require us to redistribute them and accept compounding license obligations.
2. **Size** — even 1B models are ~700MB. We don't want to bloat the repo.
3. **Choice** — different families have different hardware and language needs.
4. **Auditability** — pulls happen from the model author's own distribution, where you can verify checksums against their publication.

## How models are pulled

The installer (or `ollama pull <model>` after install) downloads weights from `https://ollama.com/library/<model>`. Ollama verifies SHA-256 checksums against its registry. No GuardianNode-controlled server is involved in this flow.

## Replacing recommended models

You can use any model Ollama supports. Set the model in the dashboard's **Model Settings** page or edit `backend/models.yaml`. The classifier prompt is model-agnostic; quality varies. Open an issue with comparison results if you find a better model for safety classification.

## Adversarial input handling

A local LLM run via Ollama is not a security boundary. Treat its output as an *oracle hint*, not as ground truth. GuardianNode validates returned JSON, applies a rules-engine override for high-confidence patterns, and shows the parent the raw evidence so they can judge for themselves.
