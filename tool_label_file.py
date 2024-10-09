import os
import threading
import tkinter as tk
from tkinter import messagebox
from pydub import AudioSegment
from io import BytesIO
import pygame

class LabelLogic:
    def __init__(self, master, audio_file, segment_duration=60):
        self.master = master
        self.master.title("Label File")
        self.audio_file = audio_file
        self.segment_duration = segment_duration
        self.classifications = []
        self.ad_segments = []
        self.queue = []
        self.current_segment = None
        self.play_thread = None
        self.is_paused = False
        self.pause_event = threading.Event()
        self.pause_event.set()
        pygame.mixer.init()
        self.load_audio()
        self.create_widgets()
        self.load_initial_segments()
        self.process_next_segment()
        self.master.bind('<a>', lambda event: self.classify("A"))
        self.master.bind('<b>', lambda event: self.classify("B"))

    def load_audio(self):
        try:
            self.audio = AudioSegment.from_mp3(self.audio_file)
            self.total_duration = len(self.audio) // 1000
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio file: {e}")
            self.master.destroy()

    def create_widgets(self):
        self.status_label = tk.Label(self.master, text="Loading...", font=("Helvetica", 14))
        self.status_label.pack(pady=10)
        self.end_time_label = tk.Label(self.master, text="", font=("Helvetica", 12))
        self.end_time_label.pack(pady=5)
        self.button_frame = tk.Frame(self.master)
        self.ad_button = tk.Button(self.button_frame, text="Ad", width=10, command=lambda: self.classify("A"))
        self.content_button = tk.Button(self.button_frame, text="Broadcast", width=10, command=lambda: self.classify("B"))
        #self.pause_button = tk.Button(self.button_frame, text="Pause", width=10, command=self.toggle_pause)
        self.ad_button.pack(side=tk.LEFT, padx=10)
        self.content_button.pack(side=tk.LEFT, padx=10)
        #self.pause_button.pack(side=tk.LEFT, padx=10)
        self.button_frame.pack(pady=20)
        total_formatted = self.format_time(self.total_duration)
        self.end_time_label.config(text=f"-2, 13-19, 23-29, 39-47, 50-")
        self.status_label.config(text="Press 'A' for Ad, 'B' for Broadcast.")

    def load_initial_segments(self):
        num_segments = self.total_duration // self.segment_duration
        for i in range(num_segments):
            start = i * self.segment_duration
            end = start + self.segment_duration
            self.queue.append({'start': start, 'end': end})
        remaining = self.total_duration % self.segment_duration
        if remaining > 0:
            self.queue.append({'start': num_segments * self.segment_duration, 'end': self.total_duration})

    def process_next_segment(self):
        if not self.queue:
            self.finish_classification()
            return
        self.current_segment = self.queue.pop(0)
        total_formatted = self.format_time(self.total_duration)
        self.status_label.config(
            text=f"Playing segment {self.format_time(self.current_segment['start'])} of {total_formatted}"
        )
        segment = self.audio[self.current_segment['start'] * 1000 : self.current_segment['end'] * 1000]
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
        self.classifications.append({
            'start': self.current_segment['start'],
            'end': self.current_segment['end'],
            'label': classification
        })
        self.process_next_segment()

    def toggle_pause(self):
        if not self.is_paused:
            self.is_paused = True
            self.pause_event.clear()
            self.pause_button.config(text="Resume")
            if hasattr(self, 'current_sound'):
                self.current_sound.pause()
        else:
            self.is_paused = False
            self.pause_event.set()
            self.pause_button.config(text="Pause")
            if hasattr(self, 'current_sound'):
                self.current_sound.unpause()

    def finish_classification(self):
        if not self.classifications:
            self.save_ad_segments([])
            messagebox.showinfo("Done", "No segments classified")
            self.master.destroy()
            return
        merged_classifications = []
        current = self.classifications[0].copy()
        for seg in self.classifications[1:]:
            if seg['label'] == current['label']:
                current['end'] = seg['end']
            else:
                merged_classifications.append(current)
                current = seg.copy()
        merged_classifications.append(current)
        adjusted_classifications = self.adjust_single_segments(merged_classifications)
        adjusted_classifications = self.refine_transitions(adjusted_classifications)
        adjusted_classifications = sorted(adjusted_classifications, key=lambda x: x['start'])
        non_overlapping = []
        prev_end = 0
        for seg in adjusted_classifications:
            if seg['start'] < prev_end:
                seg['start'] = prev_end
            if seg['end'] <= seg['start']:
                continue
            non_overlapping.append(seg)
            prev_end = seg['end']
        self.save_ad_segments(non_overlapping)
        messagebox.showinfo("Done", "Classification complete")
        self.master.destroy()

    def adjust_single_segments(self, merged_classifications):
        adjusted = merged_classifications.copy()
        for i in range(3, len(adjusted)-3):
            current = adjusted[i]
            if current['label'] == "A":
                before = adjusted[i-3:i]
                after = adjusted[i+1:i+4]
                if all(seg['label'] == "C" for seg in before) and all(seg['label'] == "C" for seg in after):
                    adjusted[i]['label'] = "C"
            elif current['label'] == "C":
                before = adjusted[i-3:i]
                after = adjusted[i+1:i+4]
                if all(seg['label'] == "A" for seg in before) and all(seg['label'] == "A" for seg in after):
                    adjusted[i]['label'] = "A"
        return adjusted

    def refine_transitions(self, classifications):
        transitions = []
        for i in range(1, len(classifications)):
            if classifications[i]['label'] != classifications[i-1]['label']:
                transitions.append((i-1, classifications[i-1]['end']))
        for idx, trans_point in transitions:
            window = tk.Toplevel(self.master)
            window.title("Refine Transition")
            start_time = max(trans_point - 60, 0)
            segment = self.audio[start_time * 1000 : trans_point * 1000]
            wav_io = BytesIO()
            segment.export(wav_io, format="wav")
            wav_io.seek(0)
            pygame.mixer.music.load(wav_io)
            pygame.mixer.music.play()
            selected_time = tk.DoubleVar()

            def play_selected(value):
                pygame.mixer.music.stop()
                pygame.mixer.music.play(start=float(value))
                selected_time.set(float(value))

            def set_transition():
                new_trans = start_time + selected_time.get()
                if new_trans < classifications[idx]['start']:
                    new_trans = classifications[idx]['start']
                elif new_trans > classifications[idx]['end']:
                    new_trans = classifications[idx]['end']
                classifications[idx]['end'] = new_trans
                classifications[idx + 1]['start'] = new_trans
                window.destroy()
                
            def draw_custom_slider(canvas, value):
                canvas.delete("slider")
                width = canvas.winfo_width()
                x_pos = (value / 60) * width
                canvas.create_line(x_pos, 0, x_pos, 30, fill="black", width=2, tags="slider")

            def on_click(event):
                widget = event.widget
                click_x = event.x
                width = widget.winfo_width()
                value = (click_x / width) * 60
                selected_time.set(value)
                draw_custom_slider(widget, value)
                play_selected(value)

            def on_drag(event):
                on_click(event)
            canvas = tk.Canvas(window, width=800, height=30, bg="lightgray")
            canvas.pack(padx=20, pady=20)
            draw_custom_slider(canvas, selected_time.get())
            canvas.bind("<Button-1>", on_click)
            canvas.bind("<B1-Motion>", on_drag)
            confirm_button = tk.Button(window, text="Set Transition", command=set_transition)
            confirm_button.pack(pady=10)
            window.grab_set()
            self.master.wait_window(window)
        return classifications

    def save_ad_segments(self, classifications):
        ad_segments = [seg for seg in classifications if seg['label'] == "A"]
        if not ad_segments:
            messagebox.showinfo("Done", "No ads detected. Classification complete.")
            return
        ad_segments = sorted(ad_segments, key=lambda x: x['start'])
        merged_ad_segments = []
        current = ad_segments[0].copy()
        for seg in ad_segments[1:]:
            if seg['start'] <= current['end']:
                current['end'] = max(current['end'], seg['end'])
            else:
                merged_ad_segments.append(current)
                current = seg.copy()
        merged_ad_segments.append(current)
        formatted_ad_segments = []
        for segment in merged_ad_segments:
            start = segment['start']
            end = segment['end']
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

    def format_time(self, seconds):
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes}:{secs:02d}"

def main():
    file_name = input("Audio file name: ")
    audio_file = f"{file_name}.mp3"
    if not os.path.exists(audio_file):
        print(f"Error: Audio file not found. Enter without extension.")
        return
    root = tk.Tk()
    app = LabelLogic(root, audio_file)
    root.mainloop()

if __name__ == "__main__":
    main()

