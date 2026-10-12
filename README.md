# bili-digest · B站视频摘读 skill

把 B站视频变成能读的文字：抓字幕 → AI 总结 → 追问问答 → 导出 Markdown 笔记。

灵感来自 [MoonDigest](https://github.com/PathGao/MoonDigest)（GPL-3.0，Chrome 扩展），本仓库是其「OpenClaw skill 版」：只做 B站单视频的摘读（无收藏夹/关注功能），由 AI 直接执行。

## 功能

- **抓字幕**：B站视频字幕（人工/AI/自动），自动 wbi 签名，中文字幕优先，支持分 P 指定
- **无字幕兜底**：自动改用视频简介 + 热门评论
- **AI 总结**：一句话总结 + 带时间戳要点 + 值不值得看
- **追问问答**：基于字幕内容回答，引用时间戳定位
- **导出**：Markdown 笔记（标题/UP/链接/时长 frontmatter），可存 Obsidian

## 安装

放到 OpenClaw 的 skills 目录（如 `~/.openclaw/workspace/skills/`）即可：

```bash
git clone https://github.com/yehuoshun/bili-digest.git
# 或直接拷贝 bili-digest/ 目录
```

## 配置

B站只给登录用户返回字幕，需要提供 B站 cookie（含 `SESSDATA`）：

```bash
# 写入 cookie 文件（格式: 浏览器里复制的一条 Cookie 字符串）
# 默认路径 ~/.openclaw/secrets/bilibili-cookies.txt，可用环境变量覆盖：
export BILI_COOKIE_FILE=/path/to/your/cookies.txt
```

## 使用

给 AI 一个 B站视频链接或 BV 号，说「总结这个视频」即可。底层命令：

```bash
python3 scripts/bili_subtitle.py <BV号或URL> [--cid N] [--json out.json] [--txt out.txt]
```

脚本输出：视频信息（标题/UP/时长/分P）、字幕文本（带 `[mm:ss]` 时间戳）或简介+热评。

## 隐私

- 所有请求直接走 B站 API + 你自己的 cookie，无中间服务器
- cookie 不随仓库分发，脚本只引用路径，值在你的本地文件里
- 本 skill 只读，不修改任何 B站数据

## License

MIT
