# Sample items

`core_text_samples.jsonl` holds ten text items from the **non-test** split of the core tier, two per domain, with their
answer keys. They show the form of an item; they are not part of any score.

Each line is one item:

| Field | Meaning |
|---|---|
| `id` | jurisdiction, task family and item number |
| `domain`, `jurisdiction`, `family` | where the item sits in the benchmark |
| `as_of` | the date whose law applies |
| `language` | language of the prompt |
| `mode` | `closed_book`: answer from knowledge; `open_book`: the prompt holds the rules needed |
| `prompt` | what the model is asked |
| `answer_format` | the fields the answer must have |
| `expected` | the answer key, computed by an audited calculation engine |
| `grader` | how the answer is compared (`tolerance` is the allowed difference per numeric field) |

An item is fully correct only when every field of the answer matches `expected` within the tolerance.

Agentic items (PDF forms, mock portals, ledgers, workspaces, code) and the hard and expert client cases are not
sampled here: they are folders of documents and simulated systems, and they stay private with the test set.
