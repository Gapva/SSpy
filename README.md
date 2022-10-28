# SSPy - A python-based level editor for [SS+](https://chedski.itch.io/sound-space-plus) (or [Sound Space](https://www.roblox.com/games/2677609345/FREE-Sound-Space-Music-Rhythm))



---
## Roadmap
- [x] Basic functionality
  - [x] Loading/Saving
  - [x] Timeline
  - [x] Note display
- [x] Note placing and removing
- [x] Audio playing
  - [x] BPM markers
- [x] Waveform on timeline
- [x] .txt map save/load support
- [ ] Investigate performance issues on Windows
- [ ] Optimizations for low-end devices
- [ ] Vulnus .zip support

## FAQ:

> Why is Vulnus support at the back of the roadmap?

To put it bluntly: I don't like it. I have my reasons why.

> What platforms does this run on?

Almost any platform that supports OpenGL and Python. Windows, MacOS, and most Linux distributions should work.

> What do I do if it crashes?

Report it! My discord tag is in the crash message, but if you can't reach me from there, feel free to open an issue.\
When the program crashes, an error message is written to `crashlog.txt` in the directory you ran the program from.\
Include this in your crash report, it helps me diagnose the issue.

> How do I run it?

Install `git`, `git-lfs`, `python`, and `ffmpeg` if you haven't, then
```
git clone https://github.com/balt-dev/SSpy/ sspy
cd sspy
pip install wheel
pip install -r requirements.txt
python main.py
```

Make sure your python is up to date. I develop on Python v3.10.

## Troubleshooting

> It's crashing and complaining about a file not found when loading a map!

Check if you've added `ffmpeg` to your system PATH.

> It's giving me a divide by zero error!

You probably did something that doesn't make sense. Report the crash.

> My song file is corrupted! What do I do?

This usually happens when the level is interrupted during saving. It's good practice to make backups often.

## Notes

This is still beta software! Don't be surprised if it crashes. Report the crash to me and I'll handle it.\
The code behind the file picker was taken from https://github.com/Zygahedron/Parabox-Editor, with [explicit permission from the repository owner.][1]


[1]: https://i.imgur.com/7JyRsjb.png (Permission proof)

## Gallery
[![YT link to SSPy Demo](https://img.youtube.com/vi/30xzC9m12Xg/0.jpg)](https://www.youtube.com/watch?v=30xzC9m12Xg)\
[YouTube link]
