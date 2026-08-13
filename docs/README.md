# docs/ — media for the README

Two files go here. Both are referenced from the top of the root README.

| File | What | Status |
|---|---|---|
| `hero.gif` | 15–20s loop of one question answered end to end | **you record this** |
| `walkthrough` link | 60–90s narrated video (YouTube/Loom — a link, not a file) | optional |

---

## Recording `hero.gif`

The GIF is the only part of this repo most visitors will "read". It has one job:
show that a plain-English question becomes verified SQL and a chart, in one shot,
with no cuts.

### 1. Wake the backend first

Free tier sleeps after ~15 min idle. Record a 50-second spinner and you have
advertised the wrong thing:

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://datachat-api-wmpd.onrender.com/ready
```

Wait for `200`. Then ask one throwaway question in the UI so the model and DB
connections are hot.

### 2. Set up the shot

- Open <https://data-chat-seven.vercel.app/>
- Browser at ~1280×800, zoom 100%, no bookmarks bar, no extensions visible
- Close DevTools
- Question already typed into the box **before** you start recording — the viewer
  wants to see the *answer* stream, not your typing speed

### 3. Record

Use a good question — one with a join and a chart-worthy result:

> *Which 3 countries had the lowest life expectancy in 2022?*

Start recording, click **Ask**, stop once the chart has rendered and the
explanation is on screen. Target **15–20 seconds**.

Tools: ScreenToGif (Windows, free), or record MP4 and convert with
`ffmpeg -i in.mp4 -vf "fps=12,scale=1000:-1:flags=lanczos" -loop 0 hero.gif`.

### 4. Keep it under ~5 MB

GitHub renders inline up to a point, and a heavy GIF makes the README feel slow.
Levers, in order: crop to the app area, drop to 10–12 fps, scale to ~1000px wide,
trim dead frames at both ends.

### 5. Wire it in

1. Save as `docs/hero.gif`
2. In the root `README.md`, delete the `[ Hero GIF goes here ]` blockquote and the
   surrounding comment block
3. Uncomment: `![DataChat in action](docs/hero.gif)`
4. Commit — check it renders on github.com, not just in your editor

### What makes it good

- **One take, no cuts.** Cuts read as hiding latency.
- **Show the SQL.** Expand *Executed SQL* before you stop. The guardrailed query
  is the differentiator; a chatbot returning a chart is not.
- **End on the chart**, not on a loading state.
- **Don't speed it up.** Real latency is the honest claim, and it is good.
