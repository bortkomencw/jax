# Copyright 2021 Google LLC
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
"""Demonstrates using jax2tf with TensorFlow model server.

See README.md for instructions.
"""
import grpc  # type: ignore[import]
import json
import logging
import requests  # type: ignore[import]

from absl import app
from absl import flags

from jax.experimental.jax2tf.examples import mnist_lib  # type: ignore

import numpy as np
import tensorflow as tf  # type: ignore[import]
import tensorflow_datasets as tfds  # type: ignore[import]
from tensorflow_serving.apis import predict_pb2  # type: ignore[import]
from tensorflow_serving.apis import prediction_service_pb2_grpc


FLAGS = flags.FLAGS

flags.DEFINE_boolean(
    "use_grpc", True,
    "Use the gRPC API (default), or the HTTP REST API.")

flags.DEFINE_string(
    "model_spec_name", "",
    "The name you used to export your model to model server (e.g., mnist_flax).")

flags.DEFINE_string(
    "prediction_service_addr",
    "localhost:8500",
    "Stubby endpoint for the prediction service. If you serve your model "
    "locally using TensorFlow model server, then you can use \"localhost:8500\""
    "for the gRPC server and \"localhost:8501\" for the HTTP REST server.")

flags.DEFINE_integer("serving_batch_size", 1,
                     "Batch size for the serving request. Must match the "
                     "batch size at which the model was saved. Must divide "
                     "--count_images",
                     lower_bound=1)
flags.DEFINE_integer("count_images", 16,
                     "How many images to test.",
                     lower_bound=1)


def serving_call_mnist(images):
  """Send an RPC or REST request to the model server.

  Args:
    images: A numpy.ndarray of shape [B, 28, 28, 1] with the batch of images to
      perform inference on.

  Returns:
    A numpy.ndarray of shape [B, 10] with the one-hot inference response.
  """
  if FLAGS.use_grpc:
    channel = grpc.insecure_channel(FLAGS.prediction_service_addr)
    stub = prediction_service_pb2_grpc.PredictionServiceStub(channel)

    request = predict_pb2.PredictRequest()
    request.model_spec.name = FLAGS.model_spec_name
    request.model_spec.signature_name = tf.saved_model.DEFAULT_SERVING_SIGNATURE_DEF_KEY
    # You can see the name of the input ("inputs") in the SavedModel dump.
    request.inputs["inputs"].CopyFrom(
        tf.make_tensor_proto(images, dtype=images.dtype, shape=images.shape))
    response = stub.Predict(request)
    # We could also use response.outputs["output_0"], where "output_0" is the
    # name of the output (which you can see in the SavedModel dump.)
    # Alternatively, we just get the first output.
    outputs, = response.outputs.values()
    return tf.make_ndarray(outputs)
  else:
    # Use the HTTP REST api
    images_json = json.dumps(images.tolist())
    # You can see the name of the input ("inputs") in the SavedModel dump.
    data = f'{{"inputs": {images_json}}}'
    predict_url = f"http://{FLAGS.prediction_service_addr}/v1/models/{FLAGS.model_spec_name}:predict"
    response = requests.post(predict_url, data=data)
    if response.status_code != 200:
      msg = (f"Received error response {response.status_code} from model "
             f"server: {response.text}")
      raise ValueError(msg)
    outputs = response.json()["outputs"]
    return np.array(outputs)


def main(_):
  if FLAGS.count_images % FLAGS.serving_batch_size != 0:
    raise ValueError(f"The count_images ({FLAGS.count_images}) must be a "
                     "multiple of "
                     f"serving_batch_size ({FLAGS.serving_batch_size})")
  test_ds = mnist_lib.load_mnist(tfds.Split.TEST,
                                 batch_size=FLAGS.serving_batch_size)
  images_and_labels = tfds.as_numpy(test_ds.take(
      FLAGS.count_images // FLAGS.serving_batch_size))

  accurate_count = 0
  for batch_idx, (images, labels) in enumerate(images_and_labels):
    predictions_one_hot = serving_call_mnist(images)
    predictions_digit = np.argmax(predictions_one_hot, axis=1)
    labels_digit = np.argmax(labels, axis=1)
    accurate_count += np.sum(labels_digit == predictions_digit)
    running_accuracy = (
        100. * accurate_count / (1 + batch_idx) / FLAGS.serving_batch_size)
    logging.info(
        f" predicted digits = {predictions_digit} labels {labels_digit}. "
        f"Running accuracy {running_accuracy:.3f}%")


if __name__ == "__main__":
  app.run(main)
