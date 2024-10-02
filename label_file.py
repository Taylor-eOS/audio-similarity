import os
import threading
import tkinter as tk
from tkinter import messagebox
from pydub import AudioSegment
import pygame

class AudioClassifier:
    def __init__(self, master, audio_file, segment_duration=30, transition_duration=5):
        self.master = master
        self.master.title("Audio Classifier")
        self.audio_file = audio_file
        self.segment_duration_seconds = segment_duration
        self.segment_duration = self.segment_duration_seconds * 1000
        self.transition_segment_duration_seconds = transition_duration
        self.transition_segment_duration = self.transition_segment_duration_seconds * 1000
        self.classifications = []
        self.split_points = []
        self.current_segment = 0
        self.segments = []
        self.play_thread = None
        self.playback_stopped = threading.Event()
        self.load_audio()
        self.create_widgets()
        self.load_segments()
        self.play_segment(self.current_segment)
        self.master.bind('a', lambda event: self.classify("A"))
        self.master.bind('c', lambda event: self.classify("C"))

        pygame.mixer.init()

    def load_audio(self):
        try:
            self.audio = AudioSegment.from_mp3(self.audio_file)
            self.total_duration = len(self.audio)
            self.total_segments = self.total_duration // self.segment_duration
            remainder = self.total_duration % self.segment_duration
            if remainder > 0:
                self.total_segments += 1
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
        self.ad_button = tk.Button(self.button_frame, text="Ad", width=10, command=lambda: self.classify("A"))
        self.content_button = tk.Button(self.button_frame, text="Cont.", width=10, command=lambda: self.classify("C"))
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
            self.playback_stopped.set()
            self.play_thread.join()

        self.playback_stopped.clear()
        self.play_thread = threading.Thread(target=self.play_audio, args=(segment,))
        self.play_thread.start()

    def play_audio(self, segment):
        try:
            # Export segment to temporary WAV file
            segment.export("temp_segment.wav", format="wav")

            pygame.mixer.music.load("temp_segment.wav")
            pygame.mixer.music.play()

            while pygame.mixer.music.get_busy():
                if self.playback_stopped.is_set():
                    pygame.mixer.music.stop()
                    break
                pygame.time.Clock().tick(10)
            os.remove("temp_segment.wav")
        except Exception as e:
            print(f"Error playing audio: {e}")

    def classify(self, classification):
        self.playback_stopped.set()
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join()

        self.classifications.append(classification)
        previous_class = self.classifications[-2] if len(self.classifications) >=2 else None
        skip_segments = 0
        skip_label = None
        if previous_class:
            if previous_class == "A" and classification == "C":
                skip_duration_seconds = 240
                skip_segments = skip_duration_seconds // self.segment_duration_seconds
                skip_label = "C"
            elif previous_class == "C" and classification == "A":
                skip_duration_seconds = 120
                skip_segments = skip_duration_seconds // self.segment_duration_seconds
                skip_label = "A"
        if skip_segments >0:
            self.status_label.config(text=f"Skipped {skip_segments} segments as '{skip_label}'")
            for _ in range(skip_segments):
                self.current_segment +=1
                if self.current_segment >= self.total_segments:
                    break
                self.classifications.append(skip_label)
        self.current_segment +=1
        if self.current_segment < self.total_segments:
            self.play_segment(self.current_segment)
        else:
            self.finish_classification()

    def toggle_pause(self):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
            self.pause_button.config(text="Resume")
        else:
            pygame.mixer.music.unpause()
            self.pause_button.config(text="Pause")

    def find_split_point(self, classifications):
        best_split = None
        max_agreement = -1
        for i in range(1, len(classifications)):
            a_before = classifications[:i].count("A")
            c_before = classifications[:i].count("C")
            a_after = classifications[i:].count("A")
            c_after = classifications[i:].count("C")
            agreement = min(a_before, c_after) + min(c_before, a_after)
            if agreement > max_agreement:
                max_agreement = agreement
                best_split = i
        if best_split:
            if best_split >1 and best_split < len(classifications)-1:
                if classifications[best_split -1] != classifications[best_split] and classifications[best_split] == classifications[best_split +1]:
                    best_split -=1
        return best_split

    def handle_transitions(self, split_point):
        transition_start = (split_point -1) * self.segment_duration
        transition_end = split_point * self.segment_duration
        transition_segment = self.audio[transition_start:transition_end]
        sub_segments = []
        for i in range(0, len(transition_segment), self.transition_segment_duration):
            sub = transition_segment[i:i + self.transition_segment_duration]
            sub_segments.append(sub)
        user_classes = []
        for idx, sub in enumerate(sub_segments):
            cls = self.ask_user_for_transition(idx +1, len(sub_segments), sub)
            if cls:
                user_classes.append(cls)
        refined_split = split_point
        for i, cls in enumerate(user_classes):
            if cls == "C":
                refined_split = split_point -1 + (i * self.transition_segment_duration_seconds / self.segment_duration_seconds)
                break
        self.split_points.append(refined_split)

    def ask_user_for_transition(self, current, total, segment):
        response = []
        def on_ad():
            response.append("A")
            window.destroy()
        def on_content():
            response.append("C")
            window.destroy()
        window = tk.Toplevel(self.master)
        window.title(f"Transition Segment {current}/{total}")
        tk.Label(window, text=f"Classify transition segment {current}/{total}").pack(pady=20)
        btn_frame = tk.Frame(window)
        tk.Button(btn_frame, text="A", width=10, command=on_ad).pack(side=tk.LEFT, padx=10)
        tk.Button(btn_frame, text="C", width=10, command=on_content).pack(side=tk.LEFT, padx=10)
        btn_frame.pack(pady=20)

        # Play the sub-segment
        threading.Thread(target=self.play_transition_audio, args=(segment,)).start()

        self.master.wait_window(window)
        return response[0] if response else None

    def play_transition_audio(self, segment):
        try:
            segment.export("temp_transition.wav", format="wav")
            pygame.mixer.music.load("temp_transition.wav")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            os.remove("temp_transition.wav")
        except Exception as e:
            print(f"Error playing transition audio: {e}")

    def finish_classification(self):
        self.status_label.config(text="Calculating split points...")
        self.button_frame.pack_forget()
        split_point = self.find_split_point(self.classifications)
        if split_point:
            self.split_points.append(split_point)
            self.handle_transitions(split_point)
        with open("split_points.txt", "w") as f:
            for idx, split in enumerate(self.split_points):
                f.write(f"Split Point {idx +1}: {split}\n")
        self.status_label.config(text="Classification complete. Split points saved.")
        messagebox.showinfo("Done", "Classification complete. Split points saved to split_points.txt.")

def main():
    root = tk.Tk()
    audio_file = "1.mp3"
    if not os.path.exists(audio_file):
        messagebox.showerror("Error", "Audio file '1.mp3' not found.")
        return
    app = AudioClassifier(root, audio_file)
    root.mainloop()

if __name__ == "__main__":
    main()

