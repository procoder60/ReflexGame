# ReflexGame

A simple reflex-based game written in Python using **pygame**. The goal is to click randomly appearing targets before they vanish. As the game progresses, targets appear more quickly, and wrong clicks produce a loud beep and visual flash to increase stress on the player. It's designed to evoke anxiety and test reflexes under pressure.

## Requirements

- Python 3.8+
- `pygame` and `numpy` (see `requirements.txt`)

## Installation

```bash
python -m pip install -r requirements.txt
```

## Running

```bash
python reflex_game.py
```

Press **Space** to start. Once the game begins a tense background noise will play, and any missclick will trigger a loud beep and buzzer plus a red flash. Click the red circles as quickly as possible. Press **Esc** at any time to quit. The game lasts for 60 seconds, after which your **final score** will be displayed.

> **Audio troubleshooting**: if you don’t hear sound, ensure your system volume isn’t muted and your speakers/headphones are connected. The game initializes `pygame.mixer` at 44100 Hz stereo; most systems support this. If `pygame` prints mixer errors in the console, try updating your sound drivers or running the script on a machine with audio hardware.


Feel free to modify the configuration constants at the top of `reflex_game.py` to change difficulty or duration.