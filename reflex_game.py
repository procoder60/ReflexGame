import pygame
import random
import sys
import numpy as np
import cv2
import os

# Get screen dimensions
pygame.display.init()
screen_info = pygame.display.Info()
WIDTH = screen_info.current_w
HEIGHT = screen_info.current_h - 40  # Reduce height slightly to keep title bar visible

TARGET_RADIUS = 30
START_INTERVAL = 3000  # milliseconds between targets
MIN_INTERVAL = 300
INTERVAL_DECREMENT = 35
INTERVAL_VARIATION = 0.7  # ±50% random variation (0.5 = 0.5 to 1.5 multiplier)
TOTAL_TIME = 120  # seconds (extended to two minutes)

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
    # load calming video
    video_path = os.path.join(os.path.dirname(__file__), "CalmingVideo.mp4")
    calming_video = None
    calming_audio_sound = None
    if os.path.exists(video_path):
        try:
            calming_video = cv2.VideoCapture(video_path)
        except Exception as e:
            print(f"Failed to load video: {e}")
    
    # Only play a dedicated CalmingMusic.ogg file during the video.
    audio_extensions = ['.ogg']
    audio_files = ['CalmingMusic']
    script_dir = os.path.dirname(__file__)

    audio_loaded = False
    for audio_file in audio_files:
        for ext in audio_extensions:
            audio_path = os.path.join(script_dir, audio_file + ext)
            if os.path.exists(audio_path):
                try:
                    calming_audio_sound = pygame.mixer.Sound(audio_path)
                    calming_audio_sound.set_volume(0.5)
                    audio_loaded = True
                    print(f"Loaded calming music from: {audio_path}")
                    break
                except Exception as e:
                    print(f"Failed to load calming music from {audio_path}: {e}")
        if audio_loaded:
            break

    # silence if no dedicated calming music file exists
    if not audio_loaded:
        calming_audio_sound = None
except Exception as e:
    print("Sound generation failed:", e)

font = pygame.font.SysFont(None, 36)
large_font = pygame.font.SysFont(None, 72)

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
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
    calming_phase = False
    # add an instruction screen before the calming phase
    show_instructions = True
    # Instructions shown at beginning vs after video
    instructions_initial = [
        "Welcome to the Stressful Reflex Game!",
        "Click the red targets as they appear.",
        "Avoid wrong clicks or you'll hear beeps and buzzes!",
        "Press SPACE to begin the calming video."
    ]
    instructions_after_video = [
        "Feeling calmer?",
        "Now get ready for the game!",
        "",
        "Press SPACE to start the stressful reflex game."
    ]
    instructions = instructions_initial
    show_instructions_after_video = False
    video_was_skipped = False  # Track if video was skipped or completed
    instructions_auto_close_time = None  # Timer for auto-closing instructions
    paused = False  # Track if game is paused
    score = 0
    interval = START_INTERVAL
    # Add random variation to interval based on INTERVAL_VARIATION constant
    varied_interval = int(interval * random.uniform(1 - INTERVAL_VARIATION, 1 + INTERVAL_VARIATION))
    next_target_time = pygame.time.get_ticks() + varied_interval
    target = None
    start_ticks = None
    calming_start_ticks = None
    last_frame_time = 0
    video_frame_delay = 0
    # summary and final calming
    show_summary = False
    summary_end_time = None
    final_calm = False
    final_calm_end_time = None

    # for wrong click message
    wrong_show = False
    wrong_time = 0
    # music speed multiplier (will be multiplied on each successful hit)
    music_speed = 1.0
    # slower acceleration factor to prevent runaway tempo
    SPEED_INCREMENT = 1.02  # originally 1.05, lowered so 2‑minute game matches previous 45‑s tempo
    
    # Calculate video frame delay based on FPS
    current_frame_surface = None
    video_frame_delay = 33.33  # default to ~30 FPS
    if calming_video:
        fps = calming_video.get(cv2.CAP_PROP_FPS)
        if fps > 0:
            video_frame_delay = 1000.0 / fps  # milliseconds between frames

    def update_music(speed):
        import time
        global music_sound
        # if music already playing, fade it out to prevent pop
        if music_sound:
            try:
                music_sound.fadeout(300)
            except Exception:
                music_sound.stop()
            # Give fadeout time to complete before regenerating
            time.sleep(0.15)
        # regenerate melody with new tempo
        notes = [220, 247, 262, 294, 330]
        melody = []
        secs_per_note = 0.4 / speed
        silence_time = 0.15  # 150ms silence between notes
        
        for i, freq in enumerate(notes):
            # Generate a sine wave at this frequency
            t = np.linspace(0, secs_per_note, int(sample_rate * secs_per_note), endpoint=False)
            tone = 0.3 * np.sin(2 * np.pi * freq * t)
            
            # Apply minimal and consistent fade to all tones
            fade_samples = int(sample_rate * 0.01)  # 10ms fade
            if fade_samples > 0 and len(tone) > fade_samples * 2:
                tone[:fade_samples] *= np.linspace(0, 1, fade_samples)
                tone[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            
            melody.append(tone)
            
            # Add longer silence between notes
            silence = np.zeros(int(sample_rate * silence_time))
            melody.append(silence)
        
        melody = np.concatenate(melody)
        
        # Add initial silence at the start to avoid zero-crossing click
        initial_silence = np.zeros(int(sample_rate * 0.02))  # 20ms silence at start
        melody = np.concatenate([initial_silence, melody])
        
        # Ensure the entire melody starts and ends at zero for clean looping
        # Apply very gentle fade to loop point
        loop_fade = int(sample_rate * 0.02)  # 20ms
        if loop_fade > 0 and len(melody) > loop_fade * 2:
            melody[:loop_fade] *= np.linspace(0, 1, loop_fade)
            melody[-loop_fade:] *= np.linspace(1, 0, loop_fade)
        
        music_sound = make_sound_from_wave(melody)
        music_sound.set_volume(0.2)
        if started and music_sound:
            # start with a fade-in
            music_sound.play(-1, fade_ms=300)

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
                    # Add random variation to interval based on INTERVAL_VARIATION constant
                    varied_interval = int(interval * random.uniform(1 - INTERVAL_VARIATION, 1 + INTERVAL_VARIATION))
                    next_target_time = now + varied_interval
                    # speed up music slightly with a gentler increment
                    music_speed *= SPEED_INCREMENT
                    update_music(music_speed)
                else:
                    # clicked wrong place -> stress cue (beep + buzz + flash)
                    if beep_sound:
                        beep_sound.play(fade_ms=50)
                    if buzz_sound:
                        buzz_sound.play(fade_ms=50)
                    # show WRONG! message briefly
                    wrong_show = True
                    wrong_time = now
                    # flash red briefly
                    screen.fill((100, 0, 0))
                    pygame.display.flip()
                    pygame.time.delay(100)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if started and not paused:
                        # Pause the game and show quit confirmation
                        paused = True
                    elif paused:
                        # Quit the game
                        running = False
                    else:
                        # Exit from menus
                        running = False
                elif not started and not calming_phase and show_instructions and event.key == pygame.K_SPACE:
                    # advance from instruction screen into calming phase
                    show_instructions = False
                    calming_phase = True
                    calming_start_ticks = pygame.time.get_ticks()
                    last_frame_time = pygame.time.get_ticks()
                    # reset video to beginning and play audio
                    if calming_video:
                        calming_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    if calming_audio_sound:
                        calming_audio_sound.play(-1, fade_ms=300)
                elif paused and event.key == pygame.K_SPACE:
                    # Resume game from pause
                    paused = False
                elif show_instructions_after_video and event.key == pygame.K_SPACE:
                    # transition from post-calming instructions to game
                    show_instructions_after_video = False
                    started = True
                    start_ticks = pygame.time.get_ticks()
                    instructions_auto_close_time = None  # Clear auto-close timer
                    if calming_audio_sound:
                        calming_audio_sound.fadeout(300)
                    if calming_video:
                        calming_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    # Generate melody with initial speed and play it
                    update_music(music_speed)
                elif calming_phase and event.key == pygame.K_SPACE:
                    # skip remainder of calming video and show post-video instructions
                    calming_phase = False
                    show_instructions_after_video = True
                    video_was_skipped = True  # Mark that video was skipped
                    instructions_auto_close_time = None  # Don't auto-close if skipped
                    if calming_audio_sound:
                        calming_audio_sound.fadeout(300)
                    if calming_video:
                        calming_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    instructions = instructions_after_video

        if started and not paused and now >= next_target_time and not target:
            target = Target()

        screen.fill((30, 30, 30))

        # Handle calming phase
        if calming_phase:
            elapsed_calm = (now - calming_start_ticks) / 1000
            remaining_calm = max(0, 60 - elapsed_calm)
            
            if remaining_calm <= 0:
                # Transition from calming to instruction screen
                calming_phase = False
                show_instructions_after_video = True
                video_was_skipped = False  # Video was not skipped, played in full
                instructions_auto_close_time = now + 5000  # Auto-close after 5 seconds
                if calming_audio_sound:
                    calming_audio_sound.fadeout(300)
                if calming_video:
                    calming_video.set(cv2.CAP_PROP_POS_FRAMES, 0)  # reset video
                instructions = instructions_after_video
            else:
                # Display calming video
                if calming_video:
                    # Only read a new frame if enough time has passed
                    time_since_last_frame = now - last_frame_time
                    if time_since_last_frame >= video_frame_delay:
                        ret, frame = calming_video.read()
                        if ret:
                            last_frame_time = now
                            # Convert BGR to RGB
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            # Resize frame to fit screen
                            frame = cv2.resize(frame, (WIDTH, HEIGHT))
                            # Convert frame to pygame surface
                            current_frame_surface = pygame.image.fromstring(frame.tobytes(), frame.shape[1::-1], "RGB")
                        else:
                            # If video ends, reset it and make sure the audio is still playing
                            calming_video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            last_frame_time = now
                            if calming_audio_sound:
                                # restart audio in case it finished
                                calming_audio_sound.play(-1, fade_ms=300)
                    
                    if current_frame_surface:
                        screen.blit(current_frame_surface, (0, 0))
                    else:
                        screen.fill((20, 40, 50))  # blue background fallback
                else:
                    screen.fill((20, 40, 50))  # calming blue background fallback
                
                # Display countdown
                countdown_text = font.render(f"Starting in {remaining_calm:.0f}s", True, (200, 220, 240))
                screen.blit(countdown_text, (WIDTH // 2 - countdown_text.get_width() // 2, HEIGHT - 50))
        
        elif final_calm:
            # display final calming video for designated duration
            if now >= final_calm_end_time:
                running = False
            else:
                # behave similarly to calming_phase video display but no countdown
                if calming_video:
                    time_since_last_frame = now - last_frame_time
                    if time_since_last_frame >= video_frame_delay:
                        ret, frame = calming_video.read()
                        if ret:
                            last_frame_time = now
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            frame = cv2.resize(frame, (WIDTH, HEIGHT))
                            current_frame_surface = pygame.image.fromstring(frame.tobytes(), frame.shape[1::-1], "RGB")
                        else:
                            calming_video.set(cv2.CAP_PROP_POS_MSEC, 60000)
                            last_frame_time = now
                            if calming_audio_sound:
                                calming_audio_sound.play(-1, fade_ms=300)
                    if current_frame_surface:
                        screen.blit(current_frame_surface, (0, 0))
                    else:
                        screen.fill((20, 40, 50))
                else:
                    screen.fill((20, 40, 50))
        elif paused:
            # Show pause/quit confirmation screen with semi-transparent overlay
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(128)
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, 0))
            
            pause_text = large_font.render("PAUSED", True, (255, 255, 255))
            quit_text = font.render("Press ESC again to quit", True, (255, 100, 100))
            continue_text = font.render("Press SPACE to continue", True, (100, 255, 100))
            screen.blit(pause_text, (WIDTH // 2 - pause_text.get_width() // 2, HEIGHT // 2 - 80))
            screen.blit(quit_text, (WIDTH // 2 - quit_text.get_width() // 2, HEIGHT // 2))
            screen.blit(continue_text, (WIDTH // 2 - continue_text.get_width() // 2, HEIGHT // 2 + 80))
        
        elif not started and show_instructions:
            # draw a simple multi-line instruction screen
            y = HEIGHT // 2 - len(instructions) * 20
            for line in instructions:
                text = font.render(line, True, (255, 255, 255))
                screen.blit(text, (WIDTH // 2 - text.get_width() // 2, y))
                y += 40
        elif show_instructions_after_video:
            # Check if auto-close timer has expired
            if instructions_auto_close_time is not None and now >= instructions_auto_close_time:
                # Auto-transition to game
                show_instructions_after_video = False
                started = True
                start_ticks = pygame.time.get_ticks()
                instructions_auto_close_time = None
                update_music(music_speed)
            else:
                # draw instructions after calming video
                y = HEIGHT // 2 - len(instructions_after_video) * 20
                for line in instructions_after_video:
                    text = font.render(line, True, (255, 255, 255))
                    screen.blit(text, (WIDTH // 2 - text.get_width() // 2, y))
                    y += 40
        elif not started:
            # if instructions are already dismissed but the game hasn't started (unlikely)
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
                # stop music with fade-out
                if music_sound:
                    music_sound.fadeout(300)
                # show summary screen for 5 seconds
                if not show_summary and not final_calm:
                    show_summary = True
                    summary_end_time = now + 5000
                if show_summary:
                    over = font.render("Game Over!", True, (255, 0, 0))
                    score_final = font.render(f"Final Score: {score}", True, (255, 255, 255))
                    screen.blit(over, (WIDTH // 2 - over.get_width() // 2, HEIGHT // 2 - 40))
                    screen.blit(score_final, (WIDTH // 2 - score_final.get_width() // 2, HEIGHT // 2))
                    # hide target
                    target = None
                    # transition to final calming
                    if now >= summary_end_time:
                        show_summary = False
                        final_calm = True
                        final_calm_end_time = now + 300000  # 5 minutes
                        # start video from 1 minute in
                        if calming_video:
                            calming_video.set(cv2.CAP_PROP_POS_MSEC, 60000)
                        if calming_audio_sound:
                            calming_audio_sound.play(-1, fade_ms=300)
                        # reset any other state
                        target = None
                else:
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

    # cleanup
    if calming_video:
        calming_video.release()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
