# ReflexGame

A simple reflex-based game written in Python using **pygame**. The goal is to click randomly appearing targets before they vanish. As the game progresses, targets appear more quickly, and wrong clicks produce a loud beep and visual flash to increase stress on the player. It's designed to evoke anxiety and test reflexes under pressure.

## Requirements

- Python 3.8+
- `pygame` and `numpy` (see `requirements.txt`)

## Installation

```bash
python -m pip install -r requirements.txt
# moviepy and imageio-ffmpeg are no longer required; they remain in `requirements.txt` for backwards compatibility but the game does not use them.
> **NOTE:** the calming video’s own soundtrack is ignored completely; only a separate audio file that you provide (e.g. `CalmingMusic.mp3`) will be used during the video.  If no external audio file is present, the program generates a simple tone for the calming period.
```

## Running

```bash
python reflex_game.py
```

Press **Space** to progress through screens:

1. a brief *instruction screen* outlining how to play,
2. a calming video, and finally
3. the reflex‑game proper.

You can hit **Space** again while the calming video is playing to skip directly into the game.

If a file named `CalmingMusic.ogg` sits next to the script, it will be the **only** audio played while the calming video runs.  No other filenames are looked for, and if that file is missing or fails to load the video will be silent (no generated tone or fallback).  This keeps background audio simple and predictable.

Once the game begins a tense background noise will play, and any missclick will trigger a loud beep and buzzer plus a red flash. The music will still speed up as you hit targets, but the rate of acceleration has been reduced to keep the tempo manageable throughout the full 120‑second session. Click the red circles as quickly as possible. Press **Esc** at any time to quit. The game lasts for 120 seconds (two minutes), after which your **final score** will be displayed.

> **Audio troubleshooting**: if you don’t hear sound, ensure your system volume isn’t muted and your speakers/headphones are connected. The game initializes `pygame.mixer` at 44100 Hz stereo; most systems support this. If `pygame` prints mixer errors in the console, try updating your sound drivers or running the script on a machine with audio hardware.


Feel free to modify the configuration constants at the top of `reflex_game.py` to change difficulty or duration.