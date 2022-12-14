# SSPy - A python-based level editor for [SS+](https://chedski.itch.io/sound-space-plus), [Sound Space](https://www.roblox.com/games/2677609345/FREE-Sound-Space-Music-Rhythm), and [Vulnus](https://beat-game-dev.github.io/Vulnus/)



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
- [x] Vulnus support
- [x] In-editor playtesting
- [ ] Investigate performance issues on Windows
- [ ] Optimizations for low-end devices


## FAQ:

> What's up with the previous versions of the FAQ?

I was unreasonably angry at the Vulnus community. I don't hold those views anymore, and I'm sorry if they disturbed you.

> What platforms does this run on?

Almost any platform that supports OpenGL and Python. Windows, MacOS, and most Linux distributions should work.

> What do I do if it crashes?

Report it! My discord tag is in the crash message, but if you can't reach me from there, feel free to open an issue.\
When the program crashes, an error message is written to `crashlog.txt` in the directory you ran the program from.\
Include this in your crash report, it helps me diagnose the issue.

## Installation

First, you're going to need Python. This is developed on Python 3.10.8.
### Windows
- If you're on Windows 10, you can [get it on the Microsoft Store.](https://apps.microsoft.com/store/detail/python-310/9PJPW5LDXLZ5)
### Linux
- You can probably get Python 3.10 using your package manager.
### Universal
- If you don't fall into either of the two above, you can get it [from the official website.](https://www.python.org/downloads/release/python-3108/)

You're also going to need ffmpeg. Same story as with Python:
### Windows
- If you're on Windows 10, you can [get it on the Microsoft Store.](https://apps.microsoft.com/store/detail/ffmpeg/9NB2FLX7X7WG)
### Linux
- ffmpeg should be in your package manager.
### Universal
- You can get a download from the [ffmpeg website.](https://ffmpeg.org/download.html)

Next, you're going to need a local copy of the repository.
- If you have `git` installed, you can run `git clone https://github.com/balt-dev/SSpy/ sspy` in the command prompt to get it.
- Otherwise, you can [download and extract the repository as a zip file.](https://github.com/balt-dev/SSpy/archive/refs/heads/master.zip)

Finally, you need to install the python libraries that this runs on.\
You can do this by running `pip install -r requirements.txt` (or `pip3` if `pip` isn't found)\
in the command prompt in the directory you extracted/cloned into.
- If you get an error about missing Microsoft Visual C build tools, follow the link it gives you and install those.

If everything goes right, you should be able to run the program by running `python main.py` in the command prompt.\
If you're getting errors past that, please create a bug report.

## Troubleshooting

> It's crashing and complaining about a file not found when loading a map!

Check if you've added `ffmpeg` to your system PATH.

> It's giving me a divide by zero error!

You probably did something that doesn't make sense. Report the crash.

> My song file is corrupted! What do I do?

This usually happens when the level is interrupted during saving. It's good practice to make backups often. Not much you can do :/

## Notes

This is still beta software! Don't be surprised if it crashes. Report the crash to me and I'll handle it.\
~~The code behind the file picker was taken from https://github.com/Zygahedron/Parabox-Editor, with [explicit permission from the repository owner.][1]~~
The in-app file picker has been removed in favor of a native dialog. 

[1]: https://i.imgur.com/7JyRsjb.png (Permission proof)

## Gallery
`TODO: make a demo of the editor in action`
