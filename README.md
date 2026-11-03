<div align="center">

# 🎬 Fullwatch

**Read the whole video. Then take notes.**
**完整读完视频，再写笔记。**

A Claude skill that turns a YouTube video into accurate notes by reading its **full transcript** — never guessing from the title.

[English](#-english) · [中文](#-中文) · [Download / 下载](https://github.com/sf-ryanyan/fullwatch/releases/latest)

![License](https://img.shields.io/badge/license-MIT-green) ![Claude](https://img.shields.io/badge/Claude-Skill-orange) ![Output](https://img.shields.io/badge/output-中文%20%7C%20English-blue)

</div>

---

## 🇺🇸 English

### 🧩 The problem

Ask an AI to "summarize this YouTube video" and it often can't see the video at all. It only sees the **title, description and chapter list** — and then writes a confident summary that may be mostly guesswork.

Even when the transcript is available, long videos cause new problems:

| Pain point | What happens |
|---|---|
| 🎲 **Guessing** | The summary is built from the title and description, not what was said |
| ✂️ **Skimming** | Only the first part of a long transcript is really read |
| 💬 **Made-up quotes** | "Quotes" are paraphrased or invented |
| 💸 **Wasted tokens** | Auto-captions repeat each line two or three times |
| 📄 **Too short to use** | A one-hour talk becomes one sentence, so you still have to watch it |

### ✅ How Fullwatch solves it

| | |
|---|---|
| 🚫 **Never guesses** | Without a transcript, it gives a clearly labeled *preview* only, and tells you how to get the full notes |
| 📖 **Reads everything** | First line to last. Long videos are split into parts and every part is read |
| 🕐 **Coverage check** | A script checks that the notes cover **00:00 to the end**, with no gaps |
| 🔍 **Quote check** | Every quote in the notes is matched against the transcript; invented quotes are caught and fixed |
| ⚡ **Token-efficient** | Repeated caption lines are removed and timestamps compressed — up to ~70% fewer tokens on rolling auto-captions |
| 📝 **Notes you can use** | Default "essentials" notes keep every claim, example, number and method — enough that you don't need to rewatch |
| 🀄 **Chinese by default** | Built for the Chinese-speaking community; replies in English if you write in English |

### 🚀 How to use

**In the Claude app (chat)**

1. Paste a YouTube link.
2. You get a **⚡ quick preview** at once (title, length, the creator's description, chapter list), marked *not yet watched*.
3. For full notes, copy the transcript from YouTube (about 10 seconds): **…more → Show transcript → scroll to the end → select all → copy**, then paste it or upload it as a `.txt` file.
4. Fullwatch reads it all, checks coverage and quotes, and gives you the notes plus a downloadable `.md` file.

**In Claude Code**

Paste a link. Captions are fetched automatically — no copying needed. Videos with no captions can be transcribed locally with faster-whisper (optional; reuses models already downloaded by the Buzz app).

**Ask for a different depth any time**

- `quick` / `快速` — one-sentence summary + key points
- *(default)* — essentials: every key claim, example, number and step
- `detailed` / `详细` — section by section with all supporting detail

Follow-up questions are answered from the transcript already read, with timestamps.

### 📦 Install

**Claude app:** Settings → Capabilities → turn on **code execution and file creation** → Skills → upload [`fullwatch.zip`](https://github.com/sf-ryanyan/fullwatch/releases/latest).

**Claude Code:** unzip into `~/.claude/skills/` (Windows: `C:\Users\<you>\.claude\skills\`), so the path is `.claude/skills/fullwatch/SKILL.md`. Then install the caption tool:

```bash
pip install -U yt-dlp
# optional, for videos without captions:
pip install -U faster-whisper "av<16"
```

No API keys. No accounts. No setup questions.

### ❓ FAQ

**Why can't it fetch captions in the chat app?** The chat app runs code in a cloud sandbox that cannot reach YouTube. Copying the transcript once keeps the notes accurate instead of guessed.

**What if a video has no "Show transcript" button?** It has no captions. Use Claude Code with local transcription, or any speech-to-text tool (such as Buzz) and upload the result.

**Does it send my data anywhere?** No third-party services are used. Transcription, when used, runs on your own computer.

### 🙏 Acknowledgements

Fullwatch is an independent, from-scratch implementation. Its design was inspired by ideas from these open-source projects:

- [claude-video](https://github.com/bradautomates/claude-video) — video understanding for agents
- [didntwatch](https://github.com/ewro/didntwatch) — rolling-caption cleanup and a strict no-fabrication rule
- [video-lens](https://github.com/kar2phi/video-lens) — "read every line" reporting

Captions are fetched with [yt-dlp](https://github.com/yt-dlp/yt-dlp); local transcription uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper).

### ⚠️ Disclaimer

Fullwatch reads publicly available captions or transcripts you provide. Respect YouTube's Terms of Service and creators' rights; notes are for personal study. AI-generated notes can contain errors — check important facts against the video using the timestamps provided. Not affiliated with YouTube, Google or Anthropic.

---

## 🇨🇳 中文

### 🧩 解决什么问题

让 AI "总结这个 YouTube 视频"，它往往**根本看不到视频内容**，只能看到**标题、简介和章节目录**，然后写出一份看起来很自信、其实大部分是猜的总结。

就算拿到了字幕，长视频还会遇到这些问题：

| 痛点 | 实际情况 |
|---|---|
| 🎲 **瞎猜** | 总结来自标题和简介，不是视频里说的话 |
| ✂️ **没读完** | 长字幕只认真读了前面一部分 |
| 💬 **编造原话** | "引用"其实是改写的，甚至是编的 |
| 💸 **浪费 token** | 自动字幕每句话重复两三次 |
| 📄 **太短没用** | 1 小时的讲座只剩一句话，看完总结还得自己再看一遍 |

### ✅ Fullwatch 怎么解决

| | |
|---|---|
| 🚫 **绝不瞎猜** | 没有字幕时只给明确标注的**预览**，并告诉你怎么拿到完整笔记 |
| 📖 **完整读完** | 从第一行读到最后一行；长视频自动分段，每一段都读 |
| 🕐 **覆盖率核对** | 程序检查笔记是否覆盖 **00:00 到结尾**，不留空档 |
| 🔍 **引用核实** | 笔记里每一句原话都会在字幕里核对，编造的引用会被抓出来改正 |
| ⚡ **省 token** | 自动去掉重复字幕、压缩时间戳，滚动式自动字幕最多可省约 70% |
| 📝 **笔记真正有用** | 默认"精华版"保留所有观点、案例、数字和方法，看完不用再回去看视频 |
| 🀄 **默认中文** | 为中文社区打造；你用英文提问时会用英文回答 |

### 🚀 怎么用

**在 Claude 对话框里**

1. 粘贴一个 YouTube 链接
2. 立刻得到 **⚡ 快速预览**（标题、时长、作者简介、章节目录），并标注"尚未读取视频内容"
3. 想要完整笔记：在 YouTube 复制字幕（约 10 秒）：**"...更多" → "显示文字记录" → 滚动到最底部 → 全选复制**，粘贴发送或存成 `.txt` 上传
4. Fullwatch 完整读完、核对覆盖率和引用，给你笔记，并提供可下载的 `.md` 文件

**在 Claude Code 里**

粘贴链接即可，字幕自动获取，不用手动复制。没有字幕的视频，可以用 faster-whisper 在本地转写（可选，会自动复用 Buzz 已下载的模型）。

**随时切换详细程度**

- `快速`：一句话总结 + 要点
- *（默认）*：精华版，所有关键观点、案例、数字和步骤
- `详细`：逐段精读，保留所有细节

追问细节时，会直接根据已读的字幕回答，并标注时间点。

### 📦 安装

**Claude 对话框：** 设置 → 功能（Capabilities）→ 开启 **代码执行和文件创建** → 技能（Skills）→ 上传 [`fullwatch.zip`](https://github.com/sf-ryanyan/fullwatch/releases/latest)

**Claude Code：** 解压到 `~/.claude/skills/`（Windows：`C:\Users\你的用户名\.claude\skills\`），路径应为 `.claude/skills/fullwatch/SKILL.md`。然后安装字幕工具：

```bash
pip install -U yt-dlp
# 可选，用于没有字幕的视频：
pip install -U faster-whisper "av<16"
```

不需要 API key，不需要注册账号，不需要任何设置。

### ❓ 常见问题

**为什么对话框里不能自动拿字幕？** 对话框的代码运行在云端沙盒里，连不上 YouTube。复制一次字幕，换来的是真正读完的笔记，而不是猜出来的。

**视频没有"显示文字记录"怎么办？** 说明这个视频没有字幕。可以用 Claude Code 本地转写，或者用任何转写工具（例如 Buzz）转成文字后上传。

**会把我的数据发给别人吗？** 不使用任何第三方服务。本地转写也完全在你自己的电脑上运行。

### 🙏 致谢

Fullwatch 是从零开始独立编写的项目，设计思路受到以下开源项目的启发：

- [claude-video](https://github.com/bradautomates/claude-video)：让 AI 理解视频
- [didntwatch](https://github.com/ewro/didntwatch)：滚动字幕清理和严格的"不编造"原则
- [video-lens](https://github.com/kar2phi/video-lens)："必须读完每一行"的报告方式

字幕获取使用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，本地转写使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)。

### ⚠️ 免责声明

Fullwatch 读取的是公开字幕，或你自己提供的文字稿。请遵守 YouTube 服务条款，尊重创作者的权利，笔记仅供个人学习使用。AI 生成的笔记可能有误，重要信息请根据时间戳回到视频核对。本项目与 YouTube、Google、Anthropic 均无关联。

---

## 👤 About / 关于作者

Built by **Ryan Yan**, a data analyst.
作者：**Ryan Yan**，数据分析师。

## 📄 License / 版权

MIT License © 2026 Ryan Yan. See [LICENSE](LICENSE).
本项目采用 MIT 开源许可，© 2026 Ryan Yan。详见 [LICENSE](LICENSE)。
