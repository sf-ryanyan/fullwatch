# Notes template

Write in 简体中文 by default (or the user's language if they write in another one, or the config `output_language`). Keep key terms in English. If writing in English, translate the headings below.

## The one test

After reading the notes, the user can explain what the video argued, which examples, numbers and stories it used, and which methods or steps it gave, without rewatching. Write until that is true, then stop.

- **Keep:** the main claims and how they connect, every concrete example / case / number / name, every method or step, definitions, counter-points or caveats the speaker gives.
- **Cut:** greetings, repetition, sponsor reads, small talk, setup that adds no information.
- **No length target.** A thin 1-hour chat can be shorter than a dense 20-minute tutorial. No padding, no empty lines like "they discussed luck a lot".
- Compact wording: short bullets, no tables unless comparing several items on the same attributes.

## Format rules

- **Section headings start with a time range:** `### [00:00–12:30] Title`. Each section starts where the previous one ended; the last ends at the video's end (or `end`). `coverage` checks this.
- Use the video's chapters as sections when present; otherwise split by topic (roughly every 10–15 min).
- **Timestamp links:** `[mm:ss](link_base + seconds)`, e.g. `[03:15](https://youtu.be/ID?t=195)`. Skip links if `link_base` is empty.
- **Quotes:** only verbatim transcript text in the original language, inside 「」, with a timestamp. Use sparingly. Never put a paraphrase in 「」 — `quotes` checks this.
- **Takeaways** fit the user's field if they mentioned one (or the config `lens`); otherwise practical takeaways anyone could act on.
- **Notes (注意)** only when needed: sponsor segments, likely caption errors, gaps with no speech, contradictions (e.g. a chapter title promises 6 items but 5 are covered).
- No opinion section unless the user asked for it.

## Template

```markdown
---
title: <title>
url: <url>
channel: <channel>
duration: <duration>
source: <source>
watched: <YYYY-MM-DD>
tags: [<3–5 broad topics>]
---

# <title>

> <channel> · <duration> · [YouTube](<url>) · 覆盖 00:00–<end> ✓

**一句话总结：** <the core claim in one sentence>

## 核心观点
<the main argument and its framework in 2–5 bullets: what is claimed, and the structure the speaker uses>

## 分段要点
### [00:00–08:40] <section title>
- <claim + the example / number / story that supports it> [03:15](<link>)
- <method or step, concrete enough to act on>

### [08:40–21:05] <section title>
- ...

## 可以直接用的做法
- <concrete action, tied to the user's lens>

## 注意
- <only if needed>
```
