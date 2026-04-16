#!/usr/bin/env python3
"""
CNN-based Jammer Bandwidth Detection for Frequency Hopping Spread Spectrum
Detects forbidden frequency bands in hop sequences using a CNN trained on synthetic data.
"""

import numpy as np
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, models, optimizers, callbacks
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
import os
from pathlib import Path


# ============================================================================
# HYPERPARAMETERS
# ============================================================================
class Config:
    # Model architecture
    INPUT_HEIGHT = 1024          # FFT bins (frequency bins)
    INPUT_WIDTH = 256            # Time steps (sequences)
    INPUT_CHANNELS = 1
    
    # Dataset generation
    NUM_SAMPLES = 2000           # Total synthetic samples
    NUM_CHANNELS = 8             # 8 frequency channels
    CHANNEL_SPACING = 200e3      # 200 kHz spacing
    JAMMING_WIDTH_MIN = 1        # Min bins in jammer (200 kHz)
    JAMMING_WIDTH_MAX = 4        # Max bins in jammer (800 kHz)
    NOISE_LEVEL = 0.05
    
    # Training parameters
    TRAIN_RATIO = 0.7
    VAL_RATIO = 0.15
    TEST_RATIO = 0.15
    BATCH_SIZE = 32
    EPOCHS = 100
    LEARNING_RATE = 1e-3
    EARLY_STOPPING_PATIENCE = 15
    
    # Data augmentation
    AUGMENT_NOISE = True
    AUGMENT_SHIFT = True
    
    # Model save path
    MODEL_DIR = Path("./models")
    MODEL_NAME = "jammer_detector_cnn"


# ============================================================================
# SYNTHETIC DATA GENERATION
# ============================================================================
class JammerDataGenerator:
    """Generate synthetic frequency hop sequences with jamming bands."""
    
    def __init__(self, config):
        self.config = config
        self.num_bins = config.INPUT_HEIGHT
        self.num_steps = config.INPUT_WIDTH
        np.random.seed(42)
    
    def generate_hop_pattern(self, seed=None):
        """
        Generate random frequency hop pattern.
        Returns: (num_steps,) array of channel indices (0-7)
        """
        if seed is not None:
            rng = np.random.RandomState(seed)
        else:
            rng = np.random
        
        hops = []
        current_channel = 0
        for _ in range(self.num_steps):
            current_channel = (current_channel + rng.randint(1, 8)) % self.config.NUM_CHANNELS
            hops.append(current_channel)
        return np.array(hops)
    
    def generate_spectrogram_with_jammer(self, hop_pattern, jammer_bin_lo, jammer_bin_hi):
        """
        Create spectrogram showing hops and jamming band.
        
        Args:
            hop_pattern: (num_steps,) array of channel indices
            jammer_bin_lo: Starting bin of jammer
            jammer_bin_hi: Ending bin of jammer (inclusive)
        
        Returns:
            spectrogram: (num_bins, num_steps) normalized spectrogram
        """
        spectrogram = np.ones((self.num_bins, self.num_steps)) * -40  # Noise floor
        
        # Place hop signals
        for t, channel in enumerate(hop_pattern):
            # Each channel has a bin location
            bin_center = int((channel / self.config.NUM_CHANNELS) * self.num_bins)
            
            # Skip if hop lands in jammer band
            if jammer_bin_lo <= bin_center <= jammer_bin_hi:
                # Suppress the hop signal in jammer band
                spectrogram[bin_center, t] = -60
            else:
                # Strong signal outside jammer band
                spectrogram[bin_center, t] = 10
        
        # Add jammer interference in forbidden band
        for t in range(self.num_steps):
            for b in range(jammer_bin_lo, jammer_bin_hi + 1):
                # Jammer appears as noise + interference
                spectrogram[b, t] = np.random.normal(5, 2)  # Mean 5 dB, std 2 dB
        
        # Add background noise
        noise = np.random.normal(0, self.config.NOISE_LEVEL, spectrogram.shape)
        spectrogram += noise
        
        return spectrogram
    
    def generate_dataset(self, num_samples):
        """
        Generate dataset of spectrograms with jammer labels.
        
        Returns:
            X: (num_samples, height, width, channels) - spectrograms
            y: (num_samples, 2) - [bin_lo_normalized, bin_hi_normalized]
        """
        X = []
        y = []
        
        for i in range(num_samples):
            # Random jammer location and width
            jammer_width = np.random.randint(
                self.config.JAMMING_WIDTH_MIN,
                self.config.JAMMING_WIDTH_MAX + 1
            )
            jammer_bin_lo = np.random.randint(0, self.num_bins - jammer_width)
            jammer_bin_hi = jammer_bin_lo + jammer_width - 1
            
            # Generate hop pattern
            hop_pattern = self.generate_hop_pattern(seed=i)
            
            # Generate spectrogram
            spec = self.generate_spectrogram_with_jammer(
                hop_pattern, jammer_bin_lo, jammer_bin_hi
            )
            
            # Normalize to [0, 1]
            spec_normalized = (spec + 60) / 70  # Assume range [-60, 10] dB
            spec_normalized = np.clip(spec_normalized, 0, 1)
            
            X.append(spec_normalized)
            
            # Normalize labels to [0, 1] as well
            y_lo = jammer_bin_lo / self.num_bins
            y_hi = jammer_bin_hi / self.num_bins
            y.append([y_lo, y_hi])
        
        X = np.array(X)
        y = np.array(y)
        
        # Add channel dimension: (num_samples, height, width) -> (num_samples, height, width, 1)
        X = np.expand_dims(X, axis=-1)
        
        return X, y


# ============================================================================
# CNN MODEL ARCHITECTURE
# ============================================================================
def build_cnn_model(config):
    """
    Build CNN model for jammer bandwidth detection.
    
    Architecture:
    - Conv blocks to extract spectral-temporal features
    - Batch normalization for stability
    - Dropout for regularization
    - Dense layers for regression output
    
    Output: [bin_lo_normalized, bin_hi_normalized] in range [0, 1]
    """
    model = models.Sequential([
        # Input layer
        layers.Input(shape=(config.INPUT_HEIGHT, config.INPUT_WIDTH, config.INPUT_CHANNELS)),
        
        # Block 1: Extract low-level frequency features
        layers.Conv2D(32, kernel_size=(5, 3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.2),
        
        # Block 2: Extract mid-level temporal patterns
        layers.Conv2D(64, kernel_size=(5, 3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.2),
        
        # Block 3: Extract high-level patterns
        layers.Conv2D(128, kernel_size=(3, 3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.MaxPooling2D(pool_size=(2, 2)),
        layers.Dropout(0.3),
        
        # Block 4: Refinement
        layers.Conv2D(64, kernel_size=(3, 3), padding='same', activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.3),
        
        # Flatten and dense layers
        layers.Flatten(),
        layers.Dense(256, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.4),
        
        layers.Dense(128, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.3),
        
        # Output layer: predict normalized bin boundaries
        layers.Dense(2, activation='sigmoid')  # Sigmoid for [0, 1] output
    ])
    
    return model


# ============================================================================
# TRAINING PIPELINE
# ============================================================================
class JammerDetectorTrainer:
    """Train, validate, and test the jammer detection CNN."""
    
    def __init__(self, config):
        self.config = config
        self.config.MODEL_DIR.mkdir(exist_ok=True)
        
        # Data generator
        self.data_gen = JammerDataGenerator(config)
        
        # Model
        self.model = None
        
        # Training history
        self.history = None
        
        # Data
        self.X_train = self.X_val = self.X_test = None
        self.y_train = self.y_val = self.y_test = None
    
    def prepare_dataset(self):
        """Generate and split dataset into train/val/test."""
        print("[*] Generating synthetic dataset...")
        X, y = self.data_gen.generate_dataset(self.config.NUM_SAMPLES)
        
        # First split: train+val vs test
        X_temp, self.X_test, y_temp, self.y_test = train_test_split(
            X, y, test_size=self.config.TEST_RATIO, random_state=42
        )
        
        # Second split: train vs val
        val_size = self.config.VAL_RATIO / (self.config.TRAIN_RATIO + self.config.VAL_RATIO)
        self.X_train, self.X_val, self.y_train, self.y_val = train_test_split(
            X_temp, y_temp, test_size=val_size, random_state=42
        )
        
        print(f"  Train set: {self.X_train.shape[0]} samples")
        print(f"  Val set:   {self.X_val.shape[0]} samples")
        print(f"  Test set:  {self.X_test.shape[0]} samples")
        
        return self.X_train, self.y_train, self.X_val, self.y_val, self.X_test, self.y_test
    
    def build_model(self):
        """Build and compile the model."""
        print("[*] Building CNN model...")
        self.model = build_cnn_model(self.config)
        
        # Compile with appropriate loss and optimizer
        optimizer = optimizers.Adam(learning_rate=self.config.LEARNING_RATE)
        
        # Use MSE loss for regression (predicting bin boundaries)
        self.model.compile(
            optimizer=optimizer,
            loss='mse',
            metrics=['mae']  # Mean absolute error in normalized units
        )
        
        print(self.model.summary())
        return self.model
    
    def train(self):
        """Train the model."""
        print("[*] Training model...")
        
        # Callbacks
        early_stop = callbacks.EarlyStopping(
            monitor='val_loss',
            patience=self.config.EARLY_STOPPING_PATIENCE,
            restore_best_weights=True,
            verbose=1
        )
        
        reduce_lr = callbacks.ReduceLROnPlateau(
            monitor='val_loss',
            factor=0.5,
            patience=5,
            min_lr=1e-6,
            verbose=1
        )
        
        model_checkpoint = callbacks.ModelCheckpoint(
            filepath=str(self.config.MODEL_DIR / f"{self.config.MODEL_NAME}_best.h5"),
            monitor='val_loss',
            save_best_only=True,
            verbose=1
        )
        
        # Train
        self.history = self.model.fit(
            self.X_train, self.y_train,
            validation_data=(self.X_val, self.y_val),
            epochs=self.config.EPOCHS,
            batch_size=self.config.BATCH_SIZE,
            callbacks=[early_stop, reduce_lr, model_checkpoint],
            verbose=1
        )
        
        # Save final model
        self.model.save(str(self.config.MODEL_DIR / f"{self.config.MODEL_NAME}_final.h5"))
        print(f"[+] Model saved to {self.config.MODEL_DIR}")
    
    def evaluate_on_test_set(self):
        """Evaluate model on held-out test set."""
        print("\n[*] Evaluating on test set...")
        test_loss, test_mae = self.model.evaluate(self.X_test, self.y_test, verbose=0)
        
        print(f"  Test Loss (MSE): {test_loss:.6f}")
        print(f"  Test MAE: {test_mae:.6f}")
        
        # Make predictions
        predictions = self.model.predict(self.X_test, verbose=0)
        
        # Convert from normalized to bin indices
        y_test_bins = self.y_test * self.config.INPUT_HEIGHT
        pred_bins = predictions * self.config.INPUT_HEIGHT
        
        # Calculate error metrics
        errors_lo = np.abs(y_test_bins[:, 0] - pred_bins[:, 0])
        errors_hi = np.abs(y_test_bins[:, 1] - pred_bins[:, 1])
        
        print(f"\n  Predicted lower bound error (bins):")
        print(f"    Mean: {np.mean(errors_lo):.2f}, Std: {np.std(errors_lo):.2f}")
        print(f"\n  Predicted upper bound error (bins):")
        print(f"    Mean: {np.mean(errors_hi):.2f}, Std: {np.std(errors_hi):.2f}")
        
        # Conversion to frequencies (assuming 4.8 MHz sample rate, 1024-point FFT)
        samp_rate = 4.8e6
        bin_hz = samp_rate / self.config.INPUT_HEIGHT
        
        freq_errors_lo = errors_lo * bin_hz / 1e3  # Convert to kHz
        freq_errors_hi = errors_hi * bin_hz / 1e3
        
        print(f"\n  Predicted frequency error (kHz):")
        print(f"    Lower bound - Mean: {np.mean(freq_errors_lo):.2f}, Std: {np.std(freq_errors_lo):.2f}")
        print(f"    Upper bound - Mean: {np.mean(freq_errors_hi):.2f}, Std: {np.std(freq_errors_hi):.2f}")
        
        return test_loss, test_mae, predictions
    
    def validate_on_new_data(self, num_new_samples=100):
        """
        Validate on completely new data not seen during training.
        This truly tests generalization.
        """
        print(f"\n[*] Validating on {num_new_samples} new unseen samples...")
        
        # Generate new data with different random seed
        np.random.seed(999)
        X_new, y_new = self.data_gen.generate_dataset(num_new_samples)
        
        # Evaluate
        val_loss, val_mae = self.model.evaluate(X_new, y_new, verbose=0)
        
        print(f"  Validation Loss (MSE): {val_loss:.6f}")
        print(f"  Validation MAE: {val_mae:.6f}")
        
        # Make predictions
        predictions = self.model.predict(X_new, verbose=0)
        
        # Denormalize
        y_new_bins = y_new * self.config.INPUT_HEIGHT
        pred_bins = predictions * self.config.INPUT_HEIGHT
        
        # Calculate error metrics
        errors_lo = np.abs(y_new_bins[:, 0] - pred_bins[:, 0])
        errors_hi = np.abs(y_new_bins[:, 1] - pred_bins[:, 1])
        
        print(f"\n  New Data - Predicted lower bound error (bins):")
        print(f"    Mean: {np.mean(errors_lo):.2f}, Std: {np.std(errors_lo):.2f}")
        print(f"    Min: {np.min(errors_lo):.2f}, Max: {np.max(errors_lo):.2f}")
        print(f"\n  New Data - Predicted upper bound error (bins):")
        print(f"    Mean: {np.mean(errors_hi):.2f}, Std: {np.std(errors_hi):.2f}")
        print(f"    Min: {np.min(errors_hi):.2f}, Max: {np.max(errors_hi):.2f}")
        
        # Show some examples
        print(f"\n  Sample predictions (first 5):")
        for i in range(min(5, num_new_samples)):
            true_lo, true_hi = y_new_bins[i]
            pred_lo, pred_hi = pred_bins[i]
            print(f"    Sample {i}: True=[{true_lo:.0f}, {true_hi:.0f}] bins, "
                  f"Pred=[{pred_lo:.0f}, {pred_hi:.0f}] bins")
        
        return val_loss, val_mae, predictions
    
    def plot_training_history(self):
        """Plot training and validation loss curves."""
        if self.history is None:
            print("[-] No training history available")
            return
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # Loss
        ax1.plot(self.history.history['loss'], label='Training Loss', linewidth=2)
        ax1.plot(self.history.history['val_loss'], label='Validation Loss', linewidth=2)
        ax1.set_xlabel('Epoch')
        ax1.set_ylabel('Loss (MSE)')
        ax1.set_title('Training and Validation Loss')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # MAE
        ax2.plot(self.history.history['mae'], label='Training MAE', linewidth=2)
        ax2.plot(self.history.history['val_mae'], label='Validation MAE', linewidth=2)
        ax2.set_xlabel('Epoch')
        ax2.set_ylabel('MAE')
        ax2.set_title('Training and Validation MAE')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(str(self.config.MODEL_DIR / 'training_history.png'), dpi=150)
        print(f"[+] Training history saved to {self.config.MODEL_DIR / 'training_history.png'}")
        plt.close()
    
    def plot_predictions(self, predictions, y_true, dataset_name="Test"):
        """Plot predicted vs true jammer boundaries."""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # Convert to bin indices
        y_true_bins = y_true * self.config.INPUT_HEIGHT
        pred_bins = predictions * self.config.INPUT_HEIGHT
        
        # Lower bound
        ax = axes[0, 0]
        ax.scatter(y_true_bins[:, 0], pred_bins[:, 0], alpha=0.5, s=30)
        ax.plot([0, self.config.INPUT_HEIGHT], [0, self.config.INPUT_HEIGHT], 'r--', label='Perfect')
        ax.set_xlabel('True Lower Boundary (bins)')
        ax.set_ylabel('Predicted Lower Boundary (bins)')
        ax.set_title(f'{dataset_name} Set - Lower Boundary Predictions')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Upper bound
        ax = axes[0, 1]
        ax.scatter(y_true_bins[:, 1], pred_bins[:, 1], alpha=0.5, s=30, color='orange')
        ax.plot([0, self.config.INPUT_HEIGHT], [0, self.config.INPUT_HEIGHT], 'r--', label='Perfect')
        ax.set_xlabel('True Upper Boundary (bins)')
        ax.set_ylabel('Predicted Upper Boundary (bins)')
        ax.set_title(f'{dataset_name} Set - Upper Boundary Predictions')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Error distribution - lower
        errors_lo = np.abs(y_true_bins[:, 0] - pred_bins[:, 0])
        ax = axes[1, 0]
        ax.hist(errors_lo, bins=30, alpha=0.7, color='blue', edgecolor='black')
        ax.set_xlabel('Prediction Error (bins)')
        ax.set_ylabel('Frequency')
        ax.set_title(f'{dataset_name} Set - Lower Bound Error Distribution\nMean: {np.mean(errors_lo):.2f} bins')
        ax.grid(True, alpha=0.3, axis='y')
        
        # Error distribution - upper
        errors_hi = np.abs(y_true_bins[:, 1] - pred_bins[:, 1])
        ax = axes[1, 1]
        ax.hist(errors_hi, bins=30, alpha=0.7, color='orange', edgecolor='black')
        ax.set_xlabel('Prediction Error (bins)')
        ax.set_ylabel('Frequency')
        ax.set_title(f'{dataset_name} Set - Upper Bound Error Distribution\nMean: {np.mean(errors_hi):.2f} bins')
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        plt.savefig(str(self.config.MODEL_DIR / f'predictions_{dataset_name.lower()}.png'), dpi=150)
        print(f"[+] Prediction plots saved to {self.config.MODEL_DIR / f'predictions_{dataset_name.lower()}.png'}")
        plt.close()


# ============================================================================
# INFERENCE CLASS FOR REAL-TIME USE
# ============================================================================
class JammerDetectorInference:
    """Perform inference on new spectrograms."""
    
    def __init__(self, model_path, config=None):
        """
        Load trained model for inference.
        
        Args:
            model_path: Path to saved model
            config: Config object (needed for denormalization)
        """
        self.model = keras.models.load_model(model_path)
        self.config = config if config is not None else Config()
        self.samp_rate = 4.8e6
        self.bin_hz = self.samp_rate / self.config.INPUT_HEIGHT
    
    def predict_jammer(self, spectrogram):
        """
        Predict jammer band from spectrogram.
        
        Args:
            spectrogram: (height, width) or (1, height, width, 1) array, normalized to [0, 1]
        
        Returns:
            dict with keys:
                - f_lo_hz: Lower frequency in Hz
                - f_hi_hz: Upper frequency in Hz
                - bin_lo: Lower bin index
                - bin_hi: Upper bin index
                - confidence: Confidence score (if available)
        """
        # Ensure correct shape
        if spectrogram.ndim == 2:
            spec = spectrogram[np.newaxis, :, :, np.newaxis]
        elif spectrogram.ndim == 3:
            spec = spectrogram[np.newaxis, :, :, :]
        else:
            spec = spectrogram
        
        # Predict
        pred_norm = self.model.predict(spec, verbose=0)[0]  # (2,)
        
        # Denormalize to bin indices
        bin_lo = int(pred_norm[0] * self.config.INPUT_HEIGHT)
        bin_hi = int(pred_norm[1] * self.config.INPUT_HEIGHT)
        
        # Ensure valid bounds
        bin_lo = max(0, min(bin_lo, self.config.INPUT_HEIGHT - 1))
        bin_hi = max(bin_lo, min(bin_hi, self.config.INPUT_HEIGHT - 1))
        
        # Convert to frequencies (assuming centered at 0 Hz)
        f_lo = (bin_lo - self.config.INPUT_HEIGHT / 2) * self.bin_hz
        f_hi = (bin_hi - self.config.INPUT_HEIGHT / 2) * self.bin_hz
        
        return {
            'f_lo_hz': f_lo,
            'f_hi_hz': f_hi,
            'bin_lo': bin_lo,
            'bin_hi': bin_hi,
            'prediction_normalized': pred_norm
        }


# ============================================================================
# MAIN EXECUTION
# ============================================================================
def main():
    """Complete training, testing, and validation pipeline."""
    
    print("=" * 80)
    print("CNN JAMMER BANDWIDTH DETECTOR - TRAINING PIPELINE")
    print("=" * 80)
    
    # Initialize
    config = Config()
    trainer = JammerDetectorTrainer(config)
    
    # Step 1: Prepare dataset
    print("\n" + "=" * 80)
    print("STEP 1: DATASET PREPARATION")
    print("=" * 80)
    X_train, y_train, X_val, y_val, X_test, y_test = trainer.prepare_dataset()
    
    # Step 2: Build model
    print("\n" + "=" * 80)
    print("STEP 2: MODEL BUILDING")
    print("=" * 80)
    trainer.build_model()
    
    # Step 3: Train
    print("\n" + "=" * 80)
    print("STEP 3: TRAINING")
    print("=" * 80)
    trainer.train()
    
    # Step 4: Evaluate on test set
    print("\n" + "=" * 80)
    print("STEP 4: TESTING ON HELD-OUT TEST SET")
    print("=" * 80)
    test_loss, test_mae, test_predictions = trainer.evaluate_on_test_set()
    
    # Step 5: Validate on new unseen data
    print("\n" + "=" * 80)
    print("STEP 5: VALIDATION ON NEW UNSEEN DATA")
    print("=" * 80)
    val_loss, val_mae, val_predictions = trainer.validate_on_new_data(num_new_samples=200)
    
    # Step 6: Visualizations
    print("\n" + "=" * 80)
    print("STEP 6: GENERATING VISUALIZATIONS")
    print("=" * 80)
    trainer.plot_training_history()
    trainer.plot_predictions(test_predictions, y_test, dataset_name="Test")
    
    # Print summary
    print("\n" + "=" * 80)
    print("TRAINING COMPLETE - SUMMARY")
    print("=" * 80)
    print(f"Model saved to: {config.MODEL_DIR / (config.MODEL_NAME + '_final.h5')}")
    print(f"Best model saved to: {config.MODEL_DIR / (config.MODEL_NAME + '_best.h5')}")
    print(f"\nTest Results:")
    print(f"  Loss: {test_loss:.6f}")
    print(f"  MAE: {test_mae:.6f}")
    print(f"\nValidation Results (New Data):")
    print(f"  Loss: {val_loss:.6f}")
    print(f"  MAE: {val_mae:.6f}")


if __name__ == '__main__':
    main()
