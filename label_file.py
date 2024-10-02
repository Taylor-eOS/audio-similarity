import os
import threading
import tkinter as tk
from tkinter import messagebox
from pydub import AudioSegment
from io import BytesIO
import pygame
import time

class LabelFile:
    def __init__(self, master, audio_file, segment_duration=30):
        self.master = master
        self.master.title("Label File")
        self.audio_file = audio_file
        self.segment_duration_seconds = segment_duration
        self.segment_duration = self.segment_duration_seconds * 1000  
        self.classifications = []
        self.transitions = []
        self.ad_segments = []  
        self.current_ad = None
        self.current_segment = 0
        self.segments = []
        self.play_thread = None
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        pygame.mixer.init()
        self.load_audio()
        self.create_widgets()
        self.load_segments()
        self.play_segment(self.current_segment)
        self.master.bind('<a>', lambda event: self.classify("A"))
        self.master.bind('<c>', lambda event: self.classify("C"))

    def load_audio(self):
        try:
            self.audio = AudioSegment.from_mp3(self.audio_file)
            self.total_duration = len(self.audio)  
            self.total_segments = self.total_duration // self.segment_duration
            if self.total_duration % self.segment_duration > 0:
                self.total_segments += 1
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio file: {e}")
            self.master.destroy()

    def load_segments(self):
        self.segments = []
        for i in range(self.total_segments):
            start_ms = i * self.segment_duration
            end_ms = start_ms + self.segment_duration
            segment = self.audio[start_ms:end_ms]
            self.segments.append(segment)

    def create_widgets(self):
        self.status_label = tk.Label(self.master, text="Loading...", font=("Helvetica", 14))
        self.status_label.pack(pady=20)
        self.button_frame = tk.Frame(self.master)
        self.ad_button = tk.Button(self.button_frame, text="Ad", width=10, command=lambda: self.classify("A"))
        self.content_button = tk.Button(self.button_frame, text="Content", width=10, command=lambda: self.classify("C"))
        self.pause_button = tk.Button(self.button_frame, text="Pause", width=10, command=self.toggle_pause)
        self.ad_button.pack(side=tk.LEFT, padx=10)
        self.content_button.pack(side=tk.LEFT, padx=10)
        self.pause_button.pack(side=tk.LEFT, padx=10)
        self.button_frame.pack(pady=20)
        self.status_label.config(text="Press 'A' for Ad or 'C' for Content.")

    def play_segment(self, index):
        if index >= self.total_segments:
            self.finish_classification()
            return

        self.status_label.config(text=f"Playing segment {index + 1}/{self.total_segments}")
        segment = self.segments[index]

        if self.play_thread and self.play_thread.is_alive():
            self.current_sound.stop()
            self.play_thread.join()

        self.play_thread = threading.Thread(target=self.play_audio, args=(segment,))
        self.play_thread.start()

    def play_audio(self, segment):
        try:
            wav_io = BytesIO()
            segment.export(wav_io, format="wav")
            wav_io.seek(0)
            self.current_sound = pygame.mixer.Sound(file=wav_io)
            self.current_sound.play()
            while pygame.mixer.get_busy():
                if not self.pause_event.is_set():
                    self.current_sound.pause()
                    self.pause_event.wait()
                    self.current_sound.unpause()
                pygame.time.Clock().tick(10)
        except Exception as e:
            print(f"Error playing audio segment: {e}")

    def classify(self, classification):
        if self.play_thread and self.play_thread.is_alive():
            self.current_sound.stop()
            self.play_thread.join()

        self.classifications.append(classification)
        previous_class = self.classifications[-2] if len(self.classifications) >= 2 else None

        if previous_class and previous_class != classification:
            transition_time_low = (self.current_segment - 1) * self.segment_duration_seconds
            transition_time_high = self.current_segment * self.segment_duration_seconds
            transition = {
                'from_type': previous_class,
                'to_type': classification,
                'low': transition_time_low,
                'high': transition_time_high
            }
            self.transitions.append(transition)
            if previous_class == 'C' and classification == 'A':
                self.current_ad = {
                    'start_time_low': transition_time_low,
                    'end_time_low': None  
                }
            elif previous_class == 'A' and classification == 'C':
                if self.current_ad is not None:
                    self.current_ad['end_time_low'] = transition_time_low
                    self.ad_segments.append(self.current_ad)
                    self.current_ad = None

        if self.current_segment >= self.total_segments:
            if self.current_ad is not None:
                self.current_ad['end_time_low'] = self.current_segment * self.segment_duration_seconds
                self.ad_segments.append(self.current_ad)
                self.current_ad = None
            self.status_label.config(text="Initial classification complete. Starting precise timing...")
            self.master.after(1000, self.precise_transition_step)  
            return

        self.current_segment += 1
        self.play_segment(self.current_segment)

    def toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            if self.current_sound:
                self.current_sound.pause()
        else:
            self.is_paused = False
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            if self.current_sound:
                self.current_sound.unpause()

    def finish_classification(self):

        if not self.transitions:
            messagebox.showinfo("Done", "No transitions detected. Classification complete.")
            self.master.destroy()
            return
        self.status_label.config(text="Initial classification complete. Starting precise timing...")
        self.master.after(1000, self.precise_transition_step)  

    def precise_transition_step(self):

        self.ad_button.config(state=tk.DISABLED)
        self.content_button.config(state=tk.DISABLED)
        self.pause_button.config(state=tk.DISABLED)

        self.status_label.config(text="Starting precise transition timing...")
        self.progress_label = tk.Label(self.master, text="", font=("Helvetica", 12))
        self.progress_label.pack(pady=10)

        self.precise_transitions = []  
        self.current_precise_index = 0
        self.total_precise = len(self.transitions)

        threading.Thread(target=self.process_precise_transitions).start()

    def process_precise_transitions(self):
        for idx, transition in enumerate(self.transitions):
            self.current_precise_index = idx + 1
            self.update_progress_label(f"Processing transition {idx + 1}/{self.total_precise}")

            if transition['from_type'] == 'C' and transition['to_type'] == 'A':

                precise_start = self.capture_precise_time(transition['low'], is_start=True)
                if precise_start is None:
                    precise_start = transition['low']  

                ad_segment = self.ad_segments[idx] if idx < len(self.ad_segments) else None
                if ad_segment:
                    ad_segment['start_precise'] = precise_start
            elif transition['from_type'] == 'A' and transition['to_type'] == 'C':

                precise_end = self.capture_precise_time(transition['low'], is_start=False)
                if precise_end is None:
                    precise_end = transition['low']  

                ad_segment = self.ad_segments[idx - 1] if idx - 1 < len(self.ad_segments) else None
                if ad_segment:
                    ad_segment['end_precise'] = precise_end

        self.save_ad_segments()
        self.update_progress_label("Precise transition timing complete.")
        messagebox.showinfo("Done", "Precise transition timing complete. Ad segments saved to ad_segments.txt.")
        self.master.destroy()

    def capture_precise_time(self, transition_time_low, is_start=True):
        event = threading.Event()
        precise_time = None

        def on_keypress(event_obj):
            nonlocal precise_time
            elapsed = time.time() - playback_start_time
            total_seconds = transition_time_low + elapsed
            total_seconds = int(round(total_seconds))  
            precise_time = total_seconds
            event.set()

        self.master.bind('<space>', on_keypress)

        pre_transition_segment_index = int(transition_time_low // self.segment_duration_seconds)
        if pre_transition_segment_index >= self.total_segments:
            pre_transition_segment_index = self.total_segments - 1
        pre_transition_segment = self.segments[pre_transition_segment_index]
        pre_transition_start_time = pre_transition_segment_index * self.segment_duration_seconds

        playback_start_time = time.time()
        def play_segment_thread():
            try:
                wav_io = BytesIO()
                pre_transition_segment.export(wav_io, format="wav")
                wav_io.seek(0)
                sound = pygame.mixer.Sound(file=wav_io)
                sound.play()
                while pygame.mixer.get_busy():
                    if not self.pause_event.is_set():
                        sound.pause()
                        self.pause_event.wait()
                        sound.unpause()
                    pygame.time.Clock().tick(10)
            except Exception as e:
                print(f"Error playing audio segment: {e}")

        play_thread = threading.Thread(target=play_segment_thread)
        play_thread.start()

        wait_time = self.segment_duration_seconds
        event_occurred = event.wait(timeout=wait_time)

        pygame.mixer.stop()
        play_thread.join()

        self.master.unbind('<space>')

        if event_occurred:
            return precise_time
        else:

            post_transition_segment_index = pre_transition_segment_index + 1
            if post_transition_segment_index >= self.total_segments:
                post_transition_segment_index = self.total_segments - 1
            post_transition_segment = self.segments[post_transition_segment_index]
            post_transition_start_time = post_transition_segment_index * self.segment_duration_seconds

            precise_time_post = None

            def on_keypress_post(event_obj):
                nonlocal precise_time_post
                elapsed_post = time.time() - playback_start_time_post
                total_seconds_post = post_transition_start_time + elapsed_post
                total_seconds_post = int(round(total_seconds_post))  
                precise_time_post = total_seconds_post
                event.set()

            self.master.bind('<space>', on_keypress_post)

            playback_start_time_post = time.time()
            def play_post_segment_thread():
                try:
                    wav_io = BytesIO()
                    post_transition_segment.export(wav_io, format="wav")
                    wav_io.seek(0)
                    sound_post = pygame.mixer.Sound(file=wav_io)
                    sound_post.play()
                    while pygame.mixer.get_busy():
                        if not self.pause_event.is_set():
                            sound_post.pause()
                            self.pause_event.wait()
                            sound_post.unpause()
                        pygame.time.Clock().tick(10)
                except Exception as e:
                    print(f"Error playing audio segment: {e}")

            play_post_thread = threading.Thread(target=play_post_segment_thread)
            play_post_thread.start()

            event_occurred_post = event.wait(timeout=self.segment_duration_seconds)

            pygame.mixer.stop()
            play_post_thread.join()

            self.master.unbind('<space>')

            if event_occurred_post:
                return precise_time_post
            else:

                return transition_time_low

    def update_progress_label(self, text):
        self.progress_label.config(text=text)

    def save_ad_segments(self):
        if not self.ad_segments:
            messagebox.showinfo("Done", "No ads detected. Classification complete.")
            self.master.destroy()
            return

        formatted_ad_segments = []
        for segment in self.ad_segments:
            start = segment.get('start_precise') or segment['start_time_low']
            end = segment.get('end_precise') or segment['end_time_low']

            start_formatted = self.format_time(start)
            end_formatted = self.format_time(end)
            formatted_ad_segments.append(f"{start_formatted}-{end_formatted}")

        try:
            with open("ad_segments.txt", "w") as f:
                filename_without_ext = os.path.splitext(self.audio_file)[0]
                f.write(f"[{filename_without_ext}]\n")
                for segment in formatted_ad_segments:
                    f.write(f"{segment}\n")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write ad segments: {e}")
            return

        self.status_label.config(text="Classification complete. Ad segments saved.")

    def format_time(self, seconds):
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"

def main():
    file_name = input("Enter the audio file name (without the extension): ")
    audio_file = f"{file_name}.mp3"
    if not os.path.exists(audio_file):
        print(f"Error: Audio file '{audio_file}' not found.")
        return
    root = tk.Tk()
    app = LabelFile(root, audio_file)
    root.mainloop()

if __name__ == "__main__":
    main()
