import os
import numpy as np
import librosa
import tensorflow as tf
import re

def parse_segments_file(segments_file_path):
    segments_dict = {}
    with open(segments_file_path, 'r') as f:
        lines = f.readlines()
        for i in range(0, len(lines), 6):
            header = lines[i].strip()
            filename_match = re.match(r'\[(.*?)\]', header)
            if filename_match:
                filename = filename_match.group(1)
                split_points = []
                for j in range(1, 6):
                    time_range = lines[i+j].strip()
                    start, end = time_range.split('-')
                    start_sec = convert_time_to_seconds(start)
                    end_sec = convert_time_to_seconds(end)
                    midpoint = (start_sec + end_sec) / 2
                    split_points.append(midpoint)
                segments_dict[filename] = split_points
    return segments_dict

def convert_time_to_seconds(time_str):
    minutes, seconds = map(int, time_str.split(':'))
    return minutes * 60 + seconds

def extract_features(audio_path, sr=22050, n_mfcc=13, hop_length=512):
    y, _ = librosa.load(audio_path, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc, hop_length=hop_length)
    mfcc = mfcc.T
    return mfcc

def generate_classification_labels(features, split_points, sr=22050, hop_length=512):
    num_frames = features.shape[0]
    frame_times = librosa.frames_to_time(np.arange(num_frames), sr=sr, hop_length=hop_length)
    labels = np.zeros(num_frames)
    for midpoint in split_points:
        idx = np.argmin(np.abs(frame_times - midpoint))
        labels[idx] = 1  # Mark the frame closest to the split point
    return labels

def create_classification_dataset(features, labels, batch_size=32):
    dataset = tf.data.Dataset.from_tensor_slices((features, labels))
    dataset = dataset.shuffle(buffer_size=1000)
    dataset = dataset.batch(batch_size)
    dataset = dataset.prefetch(tf.data.AUTOTUNE)
    return dataset

def create_regression_dataset(features, labels, batch_size=32):
    dataset = tf.data.Dataset.from_tensor_slices((features, labels))
    dataset = dataset.shuffle(buffer_size=1000)
    dataset = dataset.batch(batch_size)
    dataset = dataset.prefetch(tf.data.AUTOTUNE)
    return dataset

def prepare_regression_data(input_dir, feature_dir, segments_dict, classification_model):
    regression_features = []
    regression_labels = []
    sr = 22050
    hop_length = 512
    window_size = 30
    required_frames = int(window_size * sr / hop_length)
    regression_window_size = 180
    for audio_file in os.listdir(input_dir):
        if not audio_file.endswith('.mp3'):
            continue
        basename = os.path.splitext(audio_file)[0]
        audio_path = os.path.join(input_dir, audio_file)
        feature_path = os.path.join(feature_dir, basename + '.npy')
        features = np.load(feature_path)
        num_frames = features.shape[0]
        num_segments = num_frames // required_frames
        segments = features[:num_segments * required_frames].reshape(num_segments, required_frames, -1)
        classification_probs = classification_model.predict(segments).flatten()
        predicted_midpoints = select_transition_points(classification_probs, window_size=window_size, num_transitions=5)
        true_split_points = segments_dict.get(basename, [])
        audio_duration = librosa.get_duration(filename=audio_path)
        for midpoint in predicted_midpoints:
            start_time, duration = get_adjusted_window(midpoint, regression_window_size, audio_duration)
            segment_features = get_segment_features(features, start_time, duration, sr=sr, hop_length=hop_length)
            required_frames_reg = int(regression_window_size * sr / hop_length)
            if segment_features.shape[0] < required_frames_reg:
                pad_width = required_frames_reg - segment_features.shape[0]
                segment_features = np.pad(segment_features, ((0, pad_width), (0, 0)), mode='constant')
            regression_features.append(segment_features)
            if true_split_points:
                closest_split_point = find_closest_split_point(midpoint, true_split_points)
                regression_label = closest_split_point - start_time  # Offset within the window
                regression_labels.append(regression_label)
            else:
                continue
    return regression_features, regression_labels

def get_adjusted_window(midpoint, window_size, audio_duration):
    half_window = window_size / 2
    start_time = max(0, midpoint - half_window)
    end_time = min(audio_duration, midpoint + half_window)
    duration = end_time - start_time
    return start_time, duration

def get_segment_features(features, start_time, duration, sr=22050, hop_length=512):
    start_frame = int(librosa.time_to_frames(start_time, sr=sr, hop_length=hop_length))
    end_frame = int(librosa.time_to_frames(start_time + duration, sr=sr, hop_length=hop_length))
    return features[start_frame:end_frame, :]

def select_transition_points(probabilities, window_size=30, num_transitions=5):
    top_indices = np.argsort(probabilities)[-num_transitions:]
    midpoints = [(idx + 0.5) * window_size for idx in top_indices]
    return midpoints

def find_closest_split_point(midpoint, true_split_points):
    closest_point = min(true_split_points, key=lambda x: abs(x - midpoint))
    return closest_point

