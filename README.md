# InsightGeneration

| dir | what it is |
|---|---|
| [`LLM/`](LLM/) | The baseline harness. Every earlier attempt is replayed into the prompt. It has two arms: no insight, and the problem's editorial as the insight. |
| [`agent/`](agent/) | A tool-using agent. Submissions go into a store, and the model reads them back through tools. This is the target that `InsightGen/` evaluates against. |
| [`InsightGen/`](InsightGen/) | Insight generation loops. A generator writes an insight, the agent runs 5 times with it, and the generator sees the results and writes a better one, for 10 rounds. The generator is either an OpenAI model (`GPT/`) or the target model itself (`SelfGen/`). |

Each directory has its own README with details.