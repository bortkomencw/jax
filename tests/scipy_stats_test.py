# Copyright 2018 Google LLC
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

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import collections
import itertools

from absl.testing import absltest, parameterized

import numpy as onp
import scipy.stats as osp_stats
from scipy.stats import random_correlation

from jax import test_util as jtu
from jax.scipy import stats as lsp_stats
from lax_scipy_test import CombosWithReplacement, float_dtypes

all_shapes = [(), (4,), (3, 4), (3, 1), (1, 4), (2, 1, 4)]

def genNamedParametersNArgs(n, rng):
    return parameterized.named_parameters(
        jtu.cases_from_list(
          {"testcase_name": jtu.format_test_name_suffix("", shapes, dtypes),
            "rng": rng, "shapes": shapes, "dtypes": dtypes}
          for shapes in CombosWithReplacement(all_shapes, n)
          for dtypes in CombosWithReplacement(float_dtypes, n)))

class LaxBackedScipyStatsTests(jtu.JaxTestCase):
  """Tests for LAX-backed scipy.stats implementations"""

  @genNamedParametersNArgs(5, jtu.rand_positive())
  def testBetaLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.beta.logpdf
    lax_fun = lsp_stats.beta.logpdf

    def args_maker():
      x, a, b, loc, scale = map(rng, shapes, dtypes)
      return [x, a, b, loc, scale]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True,
                            tol=1e-4)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  @genNamedParametersNArgs(3, jtu.rand_positive())
  def testExponLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.expon.logpdf
    lax_fun = lsp_stats.expon.logpdf

    def args_maker():
      x, loc, scale = map(rng, shapes, dtypes)
      return [x, loc, scale]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  @genNamedParametersNArgs(4, jtu.rand_positive())
  def testGammaLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.gamma.logpdf
    lax_fun = lsp_stats.gamma.logpdf

    def args_maker():
      x, a, loc, scale = map(rng, shapes, dtypes)
      return [x, a, loc, scale]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  @genNamedParametersNArgs(3, jtu.rand_positive())
  def testLaplaceLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.laplace.logpdf
    lax_fun = lsp_stats.laplace.logpdf

    def args_maker():
      x, loc, scale = map(rng, shapes, dtypes)
      # clipping to ensure that scale is not too low
      scale = onp.clip(scale, a_min=0.1, a_max=None)
      return [x, loc, scale]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  # TODO: currently it ignores the argument "shapes" and only tests dim=4
  @genNamedParametersNArgs(3, jtu.rand_default())
  def testMultivariateNormalLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.multivariate_normal.logpdf
    lax_fun = lsp_stats.multivariate_normal.logpdf
    dim = 4
    shapex = (dim,)

    def args_maker():
      x, mean, cov = map(rng, (shapex, shapex, (dim, dim)), dtypes)
      cov = random_correlation.rvs(onp.arange(1, 1+dim) * 2 / (dim + 1))
      return [x, mean, cov]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True,
      tol=1e-4)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  @genNamedParametersNArgs(3, jtu.rand_default())
  def testNormLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.norm.logpdf
    lax_fun = lsp_stats.norm.logpdf

    def args_maker():
      x, loc, scale = map(rng, shapes, dtypes)
      # clipping to ensure that scale is not too low
      scale = onp.clip(onp.abs(scale), a_min=0.1, a_max=None)
      return [x, loc, scale]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

  @genNamedParametersNArgs(3, jtu.rand_default())
  def testUniformLogPdf(self, rng, shapes, dtypes):
    scipy_fun = osp_stats.uniform.logpdf
    lax_fun = lsp_stats.uniform.logpdf

    def args_maker():
      x, loc, scale = map(rng, shapes, dtypes)
      return [x, loc, onp.abs(scale)]

    self._CheckAgainstNumpy(scipy_fun, lax_fun, args_maker, check_dtypes=True)
    self._CompileAndCheck(lax_fun, args_maker, check_dtypes=True)

if __name__ == "__main__":
    absltest.main()
