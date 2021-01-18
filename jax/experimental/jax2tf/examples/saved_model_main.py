# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Demonstrates training models and saving the result as a SavedModel.

By default, uses a pure JAX implementation of MNIST. There are flags to choose
a Flax CNN version of MNIST, or to skip the training and just test a
previously saved SavedModel. It is possible to save a batch-polymorphic
version of the model, or a model prepared for specific batch sizes.
Try --help to see all flags.

This file is used both as an executable, and as a library in two other examples.
See discussion in README.md.
"""

import logging
import os

from absl import app
from absl import flags

from jax.experimental.jax2tf.examples import mnist_lib  # type: ignore
from jax.experimental.jax2tf.examples import saved_model_lib  # type: ignore

import numpy as np
import tensorflow as tf  # type: ignore
import tensorflow_datasets as tfds  # type: ignore

flags.DEFINE_string("model", "mnist_pure_jax",
                    "Which model to use: mnist_pure_jax, mnist_flax.")
flags.DEFINE_boolean("model_classifier_layer", True,
                     ("The model should include the classifier layer, or just "
                      "the last layer of logits. Set this to False when you "
                      "want to reuse the classifier-less model in a larger "
                      "model. See keras_reuse_main.py and README.md."))
flags.DEFINE_string("model_path", "/tmp/jax2tf/saved_models",
                    "Path under which to save the SavedModel.")
flags.DEFINE_integer("model_version", 1,
                     ("The version number for the SavedModel. Needed for "
                      "serving, larger versions will take precedence"))
flags.DEFINE_integer("serving_batch_size", 1,
                     ("For what batch size to prepare the serving signature. "))
flags.DEFINE_integer("num_epochs", 3, "For how many epochs to train.")
flags.DEFINE_boolean(
    "generate_model", True,
    "Train and save a new model. Otherwise, use an existing SavedModel.")
flags.DEFINE_boolean(
    "compile_model", True,
    "Enable TensorFlow jit_compiler for the SavedModel. This is "
    "necessary if you want to use the model for TensorFlow serving.")
flags.DEFINE_boolean("show_model", True, "Show details of saved SavedModel.")
flags.DEFINE_boolean(
    "show_images", False,
    "Plot some sample images with labels and inference results.")
flags.DEFINE_boolean(
    "test_savedmodel", True,
    "Test TensorFlow inference using the SavedModel w.r.t. the JAX model.")

FLAGS = flags.FLAGS


def train_and_save():
  logging.info("Loading the MNIST TensorFlow dataset")
  train_ds = mnist_lib.load_mnist(
      tfds.Split.TRAIN, batch_size=mnist_lib.train_batch_size)
  test_ds = mnist_lib.load_mnist(
      tfds.Split.TEST, batch_size=mnist_lib.test_batch_size)

  if FLAGS.show_images:
    mnist_lib.plot_images(train_ds, 1, 5, "Training images", inference_fn=None)

  the_model_class = pick_model_class()
  model_dir = savedmodel_dir(with_version=True)

  if FLAGS.generate_model:
    model_descr = model_description()
    logging.info(f"Generating model for {model_descr}")
    (predict_fn, predict_params) = the_model_class.train(
        train_ds,
        test_ds,
        FLAGS.num_epochs,
        with_classifier=FLAGS.model_classifier_layer)

    if FLAGS.serving_batch_size == -1:
      # Batch-polymorphic SavedModel
      input_signatures = [
          tf.TensorSpec((None,) + mnist_lib.input_shape, tf.float32),
      ]
      shape_polymorphic_input_spec = "(batch, _, _, _)"
    else:
      input_signatures = [
          # The first one will be the serving signature
          tf.TensorSpec((FLAGS.serving_batch_size,) + mnist_lib.input_shape,
                        tf.float32),
          tf.TensorSpec((mnist_lib.train_batch_size,) + mnist_lib.input_shape,
                        tf.float32),
          tf.TensorSpec((mnist_lib.test_batch_size,) + mnist_lib.input_shape,
                        tf.float32),
      ]
      shape_polymorphic_input_spec = None
    logging.info(f"Saving model for {model_descr}")
    saved_model_lib.convert_and_save_model(
        predict_fn,
        predict_params,
        model_dir,
        input_signatures=input_signatures,
        shape_polymorphic_input_spec=shape_polymorphic_input_spec,
        compile_model=FLAGS.compile_model)

    if FLAGS.test_savedmodel:
      tf_accelerator, tolerances = tf_accelerator_and_tolerances()
      with tf.device(tf_accelerator):
        logging.info("Testing savedmodel")
        pure_restored_model = tf.saved_model.load(model_dir)

        if FLAGS.show_images and FLAGS.model_classifier_layer:
          mnist_lib.plot_images(
              test_ds,
              1,
              5,
              f"Inference results for {model_descr}",
              inference_fn=pure_restored_model)

        test_input = np.ones(
            (mnist_lib.test_batch_size,) + mnist_lib.input_shape,
            dtype=np.float32)
        np.testing.assert_allclose(
            pure_restored_model(tf.convert_to_tensor(test_input)),
            predict_fn(predict_params, test_input), **tolerances)

  if FLAGS.show_model:
    def print_model(model_dir: str):
      cmd = f"saved_model_cli show --all --dir {model_dir}"
      print(cmd)
      os.system(cmd)

    print_model(model_dir)


def pick_model_class():
  """Picks one of PureJaxMNIST or FlaxMNIST."""
  if FLAGS.model == "mnist_pure_jax":
    return mnist_lib.PureJaxMNIST
  elif FLAGS.model == "mnist_flax":
    return mnist_lib.FlaxMNIST
  else:
    raise ValueError(f"Unrecognized model: {FLAGS.model}")


def model_description() -> str:
  """A short description of the picked model."""
  res = pick_model_class().name
  if not FLAGS.model_classifier_layer:
    res += " (features_only)"
  return res


def savedmodel_dir(with_version: bool = True) -> str:
  """The directory where we save the SavedModel."""
  model_dir = os.path.join(
      FLAGS.model_path,
      f"{'mnist' if FLAGS.model_classifier_layer else 'mnist_features'}"
  )
  if with_version:
    model_dir = os.path.join(model_dir, str(FLAGS.model_version))
  return model_dir


def tf_accelerator_and_tolerances():
  """Picks the TF accelerator to use and the tolerances for numerical checks."""
  tf_accelerator = (tf.config.list_logical_devices("TPU") +
                    tf.config.list_logical_devices("GPU") +
                    tf.config.list_logical_devices("CPU"))[0]
  logging.info(f"Using tf_accelerator = {tf_accelerator}")
  if tf_accelerator.device_type == "TPU":
    tolerances = dict(atol=1e-6, rtol=1e-6)
  elif tf_accelerator.device_type == "GPU":
    tolerances = dict(atol=1e-6, rtol=1e-4)
  elif tf_accelerator.device_type == "CPU":
    tolerances = dict(atol=1e-5, rtol=1e-5)
  logging.info(f"Using tolerances {tolerances}")
  return tf_accelerator, tolerances


if __name__ == "__main__":
  app.run(lambda _: train_and_save())
