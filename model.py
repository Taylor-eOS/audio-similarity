import tensorflow as tf
from tensorflow.keras import layers, models

def build_classification_model(input_shape):
    inputs = layers.Input(shape=input_shape)
    x = layers.Conv1D(64, kernel_size=3, activation='relu')(inputs)
    x = layers.MaxPooling1D(pool_size=2)(x)
    x = layers.Flatten()(x)
    x = layers.Dense(64, activation='relu')(x)
    outputs = layers.Dense(1, activation='sigmoid')(x)
    model = models.Model(inputs=inputs, outputs=outputs)
    return model

def build_regression_model(input_shape):
    inputs = layers.Input(shape=input_shape)
    x = layers.Conv1D(64, kernel_size=3, activation='relu')(inputs)
    x = layers.MaxPooling1D(pool_size=2)(x)
    x = layers.Flatten()(x)
    x = layers.Dense(64, activation='relu')(x)
    outputs = layers.Dense(1, activation='linear')(x)
    model = models.Model(inputs=inputs, outputs=outputs)
    return model

def compile_classification_model(model):
    model.compile(
        loss='binary_crossentropy',
        optimizer='adam',
        metrics=['accuracy']
    )

def compile_regression_model(model):
    model.compile(
        loss='mse',
        optimizer='adam',
        metrics=['mae']
    )

def save_model(model, model_path):
    model.save(model_path)

