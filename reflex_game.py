import pygame
import random
import sys
import numpy as np

# Configuration
WIDTH, HEIGHT = 800, 600
TARGET_RADIUS = 30
START_INTERVAL = 1500  # milliseconds between targets
MIN_INTERVAL = 300
INTERVAL_DECREMENT = 50
TOTAL_TIME = 60  # seconds

# ensure mixer is initialized before generating sounds
pygame.mixer.pre_init(44100, -16, 1, 512)
pygame.init()
try:
    pygame.mixer.init()
except Exception as e:
    print("Mixer init failed:", e)

# audio setup: beep for wrong clicks, buzz for aggravating sound, and a looping 'music' track
beep_sound = None
buzz_sound = None
music_sound = None
try:
    init = pygame.mixer.get_init()
    sample_rate = init[0] if init else 44100
    channels = init[2] if init else 1
    def make_sound_from_wave(arr):
        # arr is 1d float64 between -1 and 1
        data = (arr * 32767).astype(np.int16)
        if channels == 2:
            data = np.column_stack((data, data))
        return pygame.sndarray.make_sound(data)

    # beep tone
    freq = 440
    duration = 0.1
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    wave = 0.5 * np.sin(2 * np.pi * freq * t)
    beep_sound = make_sound_from_wave(wave)
    beep_sound.set_volume(1.0)
    # buzz tone (square wave)
    freq = 60
    duration = 0.2
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    buzz_wave = 0.5 * np.sign(np.sin(2 * np.pi * freq * t))
    buzz_sound = make_sound_from_wave(buzz_wave)
    buzz_sound.set_volume(0.7)
    # simple looping melody built from a few sine tones
    notes = [220, 247, 262, 294, 330]  # A3, B3, C4, D4, E4
    melody = []
    secs_per_note = 0.4
    for freq in notes:
        t = np.linspace(0, secs_per_note, int(sample_rate * secs_per_note), False)
        tone = 0.3 * np.sin(2 * np.pi * freq * t)
        melody.append(tone)
    melody = np.concatenate(melody)
    music_sound = make_sound_from_wave(melody)
    music_sound.set_volume(0.2)
except Exception as e:
    print("Sound generation failed:", e)

font = pygame.font.SysFont(None, 36)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Stressful Reflex Game")

clock = pygame.time.Clock()


class Target:
    def __init__(self):
        self.x = random.randint(TARGET_RADIUS, WIDTH - TARGET_RADIUS)
        self.y = random.randint(TARGET_RADIUS, HEIGHT - TARGET_RADIUS)
        self.color = (255, 0, 0)

    def draw(self, surface):
        pygame.draw.circle(surface, self.color, (self.x, self.y), TARGET_RADIUS)

    def hit(self, pos):
        px, py = pos
        return (px - self.x) ** 2 + (py - self.y) ** 2 <= TARGET_RADIUS ** 2


def main():
    running = True
    started = False
    score = 0
    interval = START_INTERVAL
    next_target_time = pygame.time.get_ticks() + interval
    target = None
    start_ticks = None

    # for wrong click message
    wrong_show = False
    wrong_time = 0
    # music speed multiplier
    music_speed = 1.0

    def update_music(speed):
        global music_sound
        # if music already playing, fade it out to prevent pop
        if music_sound:
            try:
                music_sound.fadeout(200)
            except Exception:
                music_sound.stop()
        # regenerate melody with new tempo
        notes = [220, 247, 262, 294, 330]
        melody = []
        secs_per_note = 0.4 / speed
        for freq in notes:
            t = np.linspace(0, secs_per_note, int(sample_rate * secs_per_note), False)
            tone = 0.3 * np.sin(2 * np.pi * freq * t)
            melody.append(tone)
        melody = np.concatenate(melody)
        music_sound = make_sound_from_wave(melody)
        music_sound.set_volume(0.2)
        if started and music_sound:
            # start with a short fade-in to smooth the transition
            music_sound.play(-1, fade_ms=200)

    while running:
        now = pygame.time.get_ticks()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and started:
                if target and target.hit(event.pos):
                    score += 1
                    target = None
                    interval = max(MIN_INTERVAL, interval - INTERVAL_DECREMENT)
                    next_target_time = now + interval
                    # speed up music slightly
                    music_speed *= 1.05
                    update_music(music_speed)
                else:
                    # clicked wrong place -> stress cue (beep + buzz + flash)
                    if beep_sound:
                        beep_sound.play()
                    if buzz_sound:
                        buzz_sound.play()
                    # show WRONG! message briefly
                    wrong_show = True
                    wrong_time = now
                    # flash red briefly
                    screen.fill((100, 0, 0))
                    pygame.display.flip()
                    pygame.time.delay(100)
            elif event.type == pygame.KEYDOWN:
                if not started and event.key == pygame.K_SPACE:
                    started = True
                    start_ticks = pygame.time.get_ticks()
                    # begin background music if available
                    if music_sound:
                        music_sound.play(-1)
                elif event.key == pygame.K_ESCAPE:
                    running = False

        if started and now >= next_target_time and not target:
            target = Target()

        screen.fill((30, 30, 30))

        if not started:
            intro = font.render("Press SPACE to start", True, (255, 255, 255))
            screen.blit(intro, (WIDTH // 2 - intro.get_width() // 2, HEIGHT // 2))
        else:
            # show wrong message if needed
            if wrong_show and now - wrong_time < 500:
                wrong_text = font.render("WRONG!", True, (255, 0, 0))
                screen.blit(wrong_text, (WIDTH // 2 - wrong_text.get_width() // 2, HEIGHT // 2 - 60))
            elif wrong_show:
                wrong_show = False
            # Time remaining
            elapsed = (now - start_ticks) / 1000
            remaining = max(0, TOTAL_TIME - elapsed)
            timer_text = font.render(f"Time: {remaining:.1f}s", True, (255, 255, 255))
            screen.blit(timer_text, (10, 10))

            score_text = font.render(f"Score: {score}", True, (255, 255, 255))
            screen.blit(score_text, (WIDTH - 150, 10))

            if remaining <= 0:
                # stop music
                if music_sound:
                    music_sound.stop()
                over = font.render("Game Over!", True, (255, 0, 0))
                score_final = font.render(f"Final Score: {score}", True, (255, 255, 255))
                prompt = font.render("Press ESC to quit", True, (255, 0, 0))
                screen.blit(over, (WIDTH // 2 - over.get_width() // 2, HEIGHT // 2 - 40))
                screen.blit(score_final, (WIDTH // 2 - score_final.get_width() // 2, HEIGHT // 2))
                screen.blit(prompt, (WIDTH // 2 - prompt.get_width() // 2, HEIGHT // 2 + 40))
                target = None
            else:
                if target:
                    target.draw(screen)
                else:
                    # show warning when no target
                    warn = font.render("...Get ready!", True, (255, 255, 0))
                    screen.blit(warn, (WIDTH // 2 - warn.get_width() // 2, HEIGHT // 2))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
