import tkinter as tk
from tkinter import messagebox
from pydub import AudioSegment
import threading
import pygame
import os

class LabelFile:
    def __init__(self, master, audio_file, segment_duration=30, fine_tune_duration=2):
        self.master = master
        self.master.title("Label File")
        self.audio_file = audio_file
        self.segment_duration_seconds = segment_duration
        self.segment_duration = self.segment_duration_seconds * 1000
        self.fine_tune_duration_seconds = fine_tune_duration
        self.fine_tune_duration = self.fine_tune_duration_seconds * 1000
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
                self.total_segments +=1
        except:
            messagebox.showerror("Error", "Failed to load audio file.")
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
        self.ad_button = tk.Button(self.button_frame, text="A", width=10, command=lambda: self.classify("A"))
        self.content_button = tk.Button(self.button_frame, text="C", width=10, command=lambda: self.classify("C"))
        self.pause_button = tk.Button(self.button_frame, text="Pause", width=10, command=self.toggle_pause)
        self.ad_button.pack(side=tk.LEFT, padx=10)
        self.content_button.pack(side=tk.LEFT, padx=10)
        self.pause_button.pack(side=tk.LEFT, padx=10)
        self.button_frame.pack(pady=20)

    def play_segment(self, index):
        if index >= self.total_segments:
            self.finish_classification()
            return
        self.status_label.config(text=f"Playing segment {index +1}/{self.total_segments}")
        segment = self.segments[index]
        if self.play_thread and self.play_thread.is_alive():
            pygame.mixer.music.stop()
            self.play_thread.join()
        self.play_thread = threading.Thread(target=self.play_audio, args=(segment,))
        self.play_thread.start()

    def play_audio(self, segment):
        try:
            segment.export("temp_segment.wav", format="wav")
            pygame.mixer.music.load("temp_segment.wav")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                if not self.pause_event.is_set():
                    pygame.mixer.music.pause()
                    self.pause_event.wait()
                    pygame.mixer.music.unpause()
                pygame.time.Clock().tick(10)
            os.remove("temp_segment.wav")
        except:
            pass

    def classify(self, classification):
        if self.play_thread and self.play_thread.is_alive():
            pygame.mixer.music.stop()
            self.play_thread.join()
        self.classifications.append(classification)
        previous_class = self.classifications[-2] if len(self.classifications) >=2 else None

        # Record transitions
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
            # Update ad segments
            if previous_class == 'C' and classification == 'A':
                # Start of an ad segment
                self.current_ad = {
                    'start_time_low': transition_time_low,
                    'start_time_high': transition_time_high
                }
            elif previous_class == 'A' and classification == 'C':
                # End of an ad segment
                if self.current_ad is not None:
                    self.current_ad['end_time_low'] = transition_time_low
                    self.current_ad['end_time_high'] = transition_time_high
                    self.ad_segments.append(self.current_ad)
                    self.current_ad = None

        # If we reach the end, and current_ad is still open, close it
        if self.current_segment >= self.total_segments:
            if self.current_ad is not None:
                self.current_ad['end_time_low'] = self.current_segment * self.segment_duration_seconds
                self.current_ad['end_time_high'] = self.current_segment * self.segment_duration_seconds
                self.ad_segments.append(self.current_ad)
                self.current_ad = None

        # Increment current segment
        self.current_segment += 1

        # Play next segment or finish
        if self.current_segment < self.total_segments:
            self.play_segment(self.current_segment)
        else:
            self.finish_classification()

    def toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            pygame.mixer.music.pause()
        else:
            self.is_paused = False
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            pygame.mixer.music.unpause()

    def finish_classification(self):
        self.status_label.config(text="Fine-tuning ad segments...")
        self.master.update()
        refined_ads = []
        for ad in self.ad_segments:
            # Fine-tune start time
            refined_start = self.find_transition(ad['start_time_low'], ad['start_time_high'], from_type='C', to_type='A')
            # Fine-tune end time
            refined_end = self.find_transition(ad['end_time_low'], ad['end_time_high'], from_type='A', to_type='C')
            refined_ads.append((refined_start, refined_end))
        formatted_ad_segments = []
        for start, end in refined_ads:
            formatted_ad_segments.append(f"{self.format_time(start)}-{self.format_time(end)}")
        try:
            with open("ad_segments.txt", "w") as f:
                for segment in formatted_ad_segments:
                    f.write(f"{segment}\n")
        except:
            messagebox.showerror("Error", "Failed to write ad segments.")
        self.status_label.config(text="Classification complete. Ad segments saved.")
        messagebox.showinfo("Done", "Classification complete. Ad segments saved to ad_segments.txt.")
        self.master.destroy()

    def find_transition(self, low, high, from_type, to_type, threshold=1):
        while high - low > threshold:
            mid = (low + high) / 2
            cls = self.ask_user_for_fine_tune(mid)
            if cls == from_type:
                low = mid
            else:
                high = mid
        return high

    def ask_user_for_fine_tune(self, start_time):
        response = []
        def on_ad():
            response.append("A")
            window.destroy()
        def on_content():
            response.append("C")
            window.destroy()
        window = tk.Toplevel(self.master)
        window.title("Fine-Tuning")
        tk.Label(window, text=f"Classify segment at {self.format_time(start_time)}").pack(pady=20)
        btn_frame = tk.Frame(window)
        tk.Button(btn_frame, text="A", width=10, command=on_ad).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="C", width=10, command=on_content).pack(side=tk.LEFT, padx=10)
        btn_frame.pack(pady=20)
        threading.Thread(target=self.play_fine_tune_audio, args=(start_time, self.fine_tune_duration_seconds)).start()
        self.master.wait_window(window)
        return response[0] if response else "C"

    def play_fine_tune_audio(self, start_time, duration_seconds):
        try:
            segment = self.audio[start_time * 1000 : (start_time + duration_seconds) * 1000]
            segment.export("temp_finetune.wav", format="wav")
            pygame.mixer.music.load("temp_finetune.wav")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            os.remove("temp_finetune.wav")
        except:
            pass

    def format_time(self, seconds):
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"

def main():
    root = tk.Tk()
    audio_file = "1.mp3"
    if not os.path.exists(audio_file):
        messagebox.showerror("Error", "Audio file '1.mp3' not found.")
        return
    app = LabelFile(root, audio_file)
    root.mainloop()

if __name__ == "__main__":
    main()

