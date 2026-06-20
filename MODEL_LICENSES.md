# Ollama Model Licenses

GuardianNode does not bundle model weights and does not claim ownership of any
third-party model weights.

Models are pulled by Ollama from model authors' or registries' distribution
channels at install time or by user command. Users must review and comply with
the license, acceptable-use policy, hardware requirements, and redistribution
terms of any model they install.

Recommended models are suggestions, not redistributed GuardianNode assets.

## Suggested Text Models

| Model | Typical use | License notes |
|---|---|---|
| `llama3.2:1b` | Low-resource text classification | Review Meta Llama 3.2 license and acceptable-use policy |
| `llama3.2:3b` | Balanced local text classification | Review Meta Llama 3.2 license and acceptable-use policy |
| `qwen2.5:7b-instruct` | Larger text classification | Review Qwen license at the upstream source |
| `mistral:7b-instruct` | Larger text classification alternative | Review Mistral license at the upstream source |

## Suggested Vision Models

| Model | Typical use | License notes |
|---|---|---|
| `qwen3-vl:8b-instruct` | Vision/OCR/screenshot analysis | Review Qwen license at the upstream source |
| `llama3.2-vision:11b` | Vision analysis alternative | Review Meta Llama 3.2 license and acceptable-use policy |
| `llava:7b` | Vision analysis alternative | Review LLaVA/upstream component licenses |
| `moondream` | Smaller vision model | Review upstream license |

## Operational Notes

- Ollama model availability, names, and licenses can change over time.
- GuardianNode release artifacts should not contain model weights.
- If you redistribute a bundle, appliance, hosted service, or commercial product
  that includes model weights, you are responsible for those model licenses.
- A local LLM is not a security boundary. GuardianNode validates and merges
  model output with rules, but parents remain responsible for reviewing evidence.
