import logging
import unittest
import numpy as np
import pandas as pd
from sklearn.naive_bayes import GaussianNB
from numpy.testing import assert_array_equal
from pandas.util.testing import assert_frame_equal
from sklearn.cluster import DBSCAN
from sklearn.linear_model import LinearRegression
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import GridSearchCV
from pipegraph.paella import Paella
from pipegraph.base import (PipeGraphRegressor,
                            PipeGraphClassifier,
                            PipeGraph,
                            Process,
                            wrap_adaptee_in_process,
                            build_graph,
                            make_connections_when_not_provided_to_init,
                            )
from pipegraph.adapters import AdapterForFitTransformAdaptee, AdapterForFitPredictAdaptee, \
    AdapterForAtomicFitPredictAdaptee
from pipegraph.standard_blocks import Concatenator, CustomCombination, TrainTestSplit, ColumnSelector

logging.basicConfig(level=logging.NOTSET)
logger = logging.getLogger(__name__)



class TestPaella(unittest.TestCase):
    def setUp(self):
        self.size = 100
        self.X = pd.DataFrame(dict(X=np.random.rand(self.size, )))
        self.y = pd.DataFrame(dict(y=np.random.rand(self.size, )))
        concatenator = Concatenator()
        gaussian_clustering = GaussianMixture(n_components=3)
        dbscan = DBSCAN(eps=0.5)
        mixer = CustomCombination()
        paellaModel = Paella(regressor=LinearRegression,
                             noise_label=None,
                             max_it=10,
                             regular_size=100,
                             minimum_size=30,
                             width_r=0.95,
                             power=10,
                             random_state=42)
        linear_model = LinearRegression()
        steps = [('Concatenate_Xy', concatenator),
                 ('Gaussian_Mixture', gaussian_clustering),
                 ('Dbscan', dbscan),
                 ('Combine_Clustering', mixer),
                 ('Paella', paellaModel),
                 ('Regressor', linear_model),
                 ]

        connections = {
            'Concatenate_Xy': dict(df1='X',
                                   df2='y'),

            'Gaussian_Mixture': dict(X=('Concatenate_Xy', 'predict')),

            'Dbscan': dict(X=('Concatenate_Xy', 'predict')),

            'Combine_Clustering': dict(
                dominant=('Dbscan', 'predict'),
                other=('Gaussian_Mixture', 'predict')),

            'Paella': dict(X='X', y='y', classification=('Combine_Clustering', 'predict')),

            'Regressor': dict(X='X', y='y', sample_weight=('Paella', 'predict'))
        }
        self.steps = steps
        self.connections = connections
        self.pgraph = PipeGraph(steps=steps, fit_connections=connections)

    def test_Paella__init(self):
        self.assertTrue(isinstance(self.pgraph._processes['Paella']._strategy._adaptee, Paella))

    def test_Paella__under_fit__Paella__fit(self):
        pgraph = self.pgraph
        pgraph._fit_data = {('_External', 'X'): self.X,
                            ('_External', 'y'): self.y,
                            }
        pgraph._fit('Concatenate_Xy')
        pgraph._fit('Gaussian_Mixture')
        pgraph._fit('Dbscan')
        pgraph._fit('Combine_Clustering')

        paellador = pgraph._processes['Paella']._strategy._adaptee

        X = pgraph._fit_data[('_External', 'X')]
        y = pgraph._fit_data[('_External', 'y')]
        classification = pgraph._fit_data[('Combine_Clustering', 'predict')]
        paellador.fit(X, y, classification)

    def test_Paella__under_predict__Paella__fit(self):
        pgraph = self.pgraph
        pgraph._fit_data = {('_External', 'X'): self.X,
                            ('_External', 'y'): self.y, }
        pgraph._fit('Concatenate_Xy')
        pgraph._fit('Gaussian_Mixture')
        pgraph._fit('Dbscan')
        pgraph._fit('Combine_Clustering')
        pgraph._fit('Paella')

        X = pgraph._fit_data[('_External', 'X')]
        y = pgraph._fit_data[('_External', 'y')]
        paellador = pgraph._processes['Paella']._strategy._adaptee
        result = paellador.transform(X=X, y=y)
        self.assertEqual(result.shape[0], self.size)

    def test_Paella__get_params(self):
        pgraph = self.pgraph
        paellador = pgraph._processes['Paella']
        result = paellador.get_params()['minimum_size']
        self.assertEqual(result, 30)

    def test_Paella__set_params(self):
        pgraph = self.pgraph
        paellador = pgraph._processes['Paella']
        result_pre = paellador.get_params()['max_it']
        self.assertEqual(result_pre, 10)
        result_post = paellador.set_params(max_it=1000).get_params()['max_it']
        self.assertEqual(result_post, 1000)


class TestTrainTestSplit(unittest.TestCase):
    def setUp(self):
        self.X = [1, 2, 3, 4, 5, 6, 7, 8]
        self.y = [101, 200, 300, 400, 500, 600, 700, 800]

    def test_train_test_predict(self):
        tts = TrainTestSplit()
        step = wrap_adaptee_in_process(tts)
        result = step.predict(X=self.X, y=self.y)
        self.assertEqual(len(result), 4)
        self.assertEqual(sorted(list(result.keys())),
                         sorted(['X_train', 'X_test', 'y_train', 'y_test']))
        self.assertEqual(len(result['X_train']), 6)
        self.assertEqual(len(result['X_test']), 2)
        self.assertEqual(len(result['y_train']), 6)
        self.assertEqual(len(result['y_test']), 2)


class TestColumnSelector(unittest.TestCase):
    def setUp(self):
        self.X = pd.DataFrame.from_dict({'V1':[1, 2, 3, 4, 5, 6, 7, 8],
                               'V2':[10, 20, 30, 40, 50, 60, 70, 80],
                               'V3':[100, 200, 300, 400, 500, 600, 700, 800]})

    def test_ColumnSelector__mapping_is_None(self):
        X = self.X
        selector = ColumnSelector()
        self.assertTrue(selector.fit() is selector)
        assert_frame_equal(selector.predict(X)['predict'], X)

    def test_ColumnSelector__pick_one_column_first(self):
        X = self.X
        selector = ColumnSelector(mapping={'X': slice(0,1)})
        self.assertTrue(selector.fit() is selector)
        assert_frame_equal(selector.predict(X)['X'], X.loc[:, ["V1"]])


    def test_ColumnSelector__pick_one_column_last(self):
        X = self.X
        selector = ColumnSelector(mapping={'y': slice(2, 3)})
        self.assertTrue(selector.fit() is selector)
        assert_frame_equal(selector.predict(X)['y'], X.loc[:, ["V3"]])

    def test_ColumnSelector__pick_two_columns(self):
        X = self.X
        selector = ColumnSelector(mapping={'X': slice(0, 2)})
        self.assertTrue(selector.fit() is selector)
        assert_frame_equal(selector.predict(X)['X'], X.loc[:, ["V1", "V2"]])


    def test_ColumnSelector__pick_three_columns(self):
        X = self.X
        selector = ColumnSelector(mapping={'X': slice(0, 3)})
        self.assertTrue(selector.fit() is selector)
        assert_frame_equal(selector.predict(X)['X'], X)

if __name__ == '__main__':
    unittest.main()