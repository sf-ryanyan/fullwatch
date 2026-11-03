# When the transcript cannot be fetched automatically

Two parts, in this order: a **快速预览** from the video page, then a short guide for copying the transcript. Write both in the user's language (Chinese by default).

## Part 1 — 快速预览 (preview)

Use only what the video page really shows. Fetch the page with your web page fetch tool if available; if you have none, skip the preview and go to Part 2.

**Allowed:** title, channel, length, a short paraphrase of the creator's own description (say it comes from the description), the chapter list with timestamps.
**Not allowed:** anything presented as what the speaker said; guessed claims, examples or numbers; wording that makes the preview look like full notes. Do not copy long passages of the description.

If the page has no chapters and only a thin description, keep the preview to two lines and say there is little to go on.

Format:

```markdown
**⚡ 快速预览**（基于标题、简介和章节目录，尚未读取视频内容）
- **视频：** <title> · <channel> · <length>
- **作者简介提到：** <1–3 lines, paraphrased>
- **章节结构：** 00:00 <chapter> → 04:34 <chapter> → …
```

## Part 2 — how to copy the transcript (show this)

📌 **想要完整笔记**（所有观点、案例、数字、方法），请复制一下字幕，约 10 秒：

**电脑浏览器：**
1. 打开视频，点视频下方简介里的 **"...更多"**
2. 往下找到并点击 **"显示文字记录"**（英文界面是 **Show transcript**）
3. 右侧出现带时间的字幕：**先滚动到最底部**（长视频会边滚动边加载），再**全选复制**，粘贴发给我；存成 .txt 文件上传更省 token

**手机：** YouTube App 里点简介 → **"显示文字记录"**。手机上很难全选，建议用电脑复制，或稍后在电脑上继续。

找不到"显示文字记录"，说明这个视频**没有字幕**。可以用转写工具（例如 Buzz）把视频转成文字文件再上传。

## Notes for Claude

- Accept whatever the user sends: copied panel text (timestamps on their own lines or inline), SRT, VTT, or plain text. Save pasted text unchanged to a `.txt` file and run `import` with `--duration` set to the length seen on the page.
- If `import` reports `transcript_may_be_incomplete`, tell the user where it stops and ask for the rest; YouTube only loads long transcripts as the panel is scrolled.
- A transcript without timestamps still works, but the coverage check cannot run; mention that in 注意.
