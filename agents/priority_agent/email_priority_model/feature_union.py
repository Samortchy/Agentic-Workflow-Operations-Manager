import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler

from .text_features import TextFeatureExtractor
from .structured_features import StructuredFeatureExtractor


class FeatureUnion(BaseEstimator, TransformerMixin):

    def __init__(self):
        self.tfidf = TfidfVectorizer(
            max_features=3000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            stop_words="english"
        )

        self.text_ext = TextFeatureExtractor()
        self.struct_ext = StructuredFeatureExtractor()
        self.scaler = StandardScaler()

    def fit(self, X, y=None):

        self.tfidf.fit(X["text"])

        self.text_ext.fit(X["text"])
        self.struct_ext.fit(X["structured"])

        text_feats = self.text_ext.transform(X["text"])
        struct_feats = self.struct_ext.transform(X["structured"])

        self.scaler.fit(
            np.hstack([text_feats, struct_feats])
        )

        return self

    def transform(self, X):

        tfidf_matrix = self.tfidf.transform(X["text"])

        text_feats = self.text_ext.transform(X["text"])
        struct_feats = self.struct_ext.transform(X["structured"])

        dense_scaled = self.scaler.transform(
            np.hstack([text_feats, struct_feats])
        )

        return hstack([
            tfidf_matrix,
            csr_matrix(dense_scaled)
        ])