import os
import argparse
import numpy as np
import tensorflow as tf
import librosa
import utils
import model

input_dir = 'input'
model_dir = 'models'
feature_dir = model_dir
segments_file = 'input/segments.txt'

def train():
    make_dirs()
    segments_dict = utils.parse_segments_file(segments_file)
    all_features = []
    all_labels = []
    for audio_file in os.listdir(input_dir):
        if not audio_file.endswith('.wav'):
            continue
        basename = os.path.splitext(audio_file)[0]
        audio_path = os.path.join(input_dir, audio_file)
        feature_path = os.path.join(feature_dir, basename + '.npy')
        if not os.path.exists(feature_path):
            features = utils.extract_features(audio_path)
            np.save(feature_path, features)
        else:
            features = np.load(feature_path)
        split_points = segments_dict.get(basename, [])
        labels = utils.generate_classification_labels(features, split_points)
        all_features.append(features)
        all_labels.append(labels)
    if not all_features:
        print("No wav files found in the input directory")
        return
    combined_features = np.concatenate(all_features, axis=0)
    combined_labels = np.concatenate(all_labels, axis=0)
    classification_dataset = utils.create_classification_dataset(combined_features, combined_labels)
    # Build and compile classification model
    input_shape = combined_features.shape[1:]
    classification_model = model.build_classification_model(input_shape)
    model.compile_classification_model(classification_model)
    # Train classification model
    print("Training classification model")
    classification_model.fit(classification_dataset, epochs=1, validation_split=0.1)
    classification_model_path = os.path.join(model_dir, 'classification_model.h5')
    model.save_model(classification_model, classification_model_path)
    print(f"Classification model saved")
    # Prepare data for regression model using classification model's predictions
    regression_features, regression_labels = utils.prepare_regression_data(input_dir, feature_dir, segments_dict, classification_model)
    if regression_features and regression_labels:
        regression_features = np.array(regression_features)
        regression_labels = np.array(regression_labels)
        regression_dataset = utils.create_regression_dataset(regression_features, regression_labels)
        # Build and compile regression model
        regression_input_shape = regression_features.shape[1:]
        regression_model = model.build_regression_model(regression_input_shape)
        model.compile_regression_model(regression_model)
        print("Training regression model")
        regression_model.fit(regression_dataset, epochs=1, validation_split=0.1)
        regression_model_path = os.path.join(model_dir, 'regression_model.h5')
        model.save_model(regression_model, regression_model_path)
        print(f"Regression model saved")
    else:
        print("No regression data available to train the regression model")

def infer(input_file):
    sr = 22050
    hop_length = 512
    window_size = 30
    regression_window_size = 180
    num_transitions = 8
    classification_model_path = os.path.join(model_dir, 'classification_model.h5')
    regression_model_path = os.path.join(model_dir, 'regression_model.h5')
    if not os.path.exists(classification_model_path) or not os.path.exists(regression_model_path):
        print("Models not found. Please train the models first.")
        return
    classification_model = tf.keras.models.load_model(classification_model_path)
    regression_model = tf.keras.models.load_model(regression_model_path)
    audio_path = os.path.join(input_dir, input_file)
    if not os.path.exists(audio_path):
        print(f"Audio file {audio_path} not found.")
        return
    basename = os.path.splitext(os.path.basename(audio_path))[0]
    feature_path = os.path.join(feature_dir, basename + '.npy')
    if not os.path.exists(feature_path):
        features = utils.extract_features(audio_path)
        np.save(feature_path, features)
    else:
        features = np.load(feature_path)
    required_frames = int(window_size * sr / hop_length)
    num_frames = features.shape[0]
    num_segments = num_frames // required_frames
    segments = features[:num_segments * required_frames].reshape(num_segments, required_frames, -1)
    classification_probs = classification_model.predict(segments).flatten()
    predicted_midpoints = utils.select_transition_points(classification_probs, window_size=window_size, num_transitions=num_transitions)
    # Predict exact timestamps using regression model
    audio_duration = librosa.get_duration(filename=audio_path)
    transition_timestamps = []
    for midpoint in predicted_midpoints:
        start_time, duration = utils.get_adjusted_window(midpoint, regression_window_size, audio_duration)
        segment_features = utils.get_segment_features(features, start_time, duration, sr=sr, hop_length=hop_length)
        required_frames_reg = int(regression_window_size * sr / hop_length)
        if segment_features.shape[0] < required_frames_reg:
            # Pad if necessary
            pad_width = required_frames_reg - segment_features.shape[0]
            segment_features = np.pad(segment_features, ((0, pad_width), (0, 0)), mode='constant')
        segment_features = np.expand_dims(segment_features, axis=0)
        regression_pred = regression_model.predict(segment_features)
        exact_timestamp = start_time + regression_pred[0][0]
        exact_timestamp = np.clip(exact_timestamp, 0, audio_duration)
        transition_timestamps.append(exact_timestamp)
    output_path = basename + '_transitions.txt'
    with open(output_path, 'w') as f:
        for ts in transition_timestamps:
            f.write(f"{ts}\n")
    print(f"Detected transition timestamps saved")

def make_dirs():
    os.makedirs(model_dir, exist_ok=True)
    os.makedirs(feature_dir, exist_ok=True)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Audio Content Style Change Detection")
    parser.add_argument('mode', type=str, choices=['train', 'infer'], help='Choose mode: training or inference')
    parser.add_argument('file', nargs='?', type=str, help='File name (without extension) for inference mode')
    return parser.parse_args()

def main():
    args = parse_arguments()
    if args.mode == 'train':
        train()
    elif args.mode == 'infer':
        if not args.file:
            print("Error: No file name provided for infer mode.")
            return
        infer(args.file)

if __name__ == "__main__":
    main()

