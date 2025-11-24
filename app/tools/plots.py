# wrappers matplotlib (1 gráfico por figura; sem paletas fixas)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from .runtime import fig_to_base64_png


def plot_histogram(df: pd.DataFrame, column: str, bins: int = 30, log_scale: bool = False) -> str:
    if column not in df.columns:
        raise ValueError(f"Coluna '{column}' não encontrada no dataset")
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    plt.figure()
    plt.hist(series, bins=bins)
    plt.title(f"Histograma – {column}")
    plt.xlabel(column)
    plt.ylabel("Frequência")
    if log_scale:
        plt.yscale("log")
    return fig_to_base64_png()


def plot_corr_heatmap(df: pd.DataFrame, method: str = "pearson") -> str:
    num_df = df.select_dtypes(include=["number"]).copy()
    corr = num_df.corr(method=method)
    plt.figure()
    plt.imshow(corr.values, aspect="auto")
    plt.xticks(range(len(corr.columns)), corr.columns, rotation=90)
    plt.yticks(range(len(corr.index)), corr.index)
    plt.title(f"Matriz de correlação ({method})")
    plt.colorbar()
    return fig_to_base64_png()