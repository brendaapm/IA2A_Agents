# funções utilitárias para HTML de DataFrame
# Conversores de DataFrame para HTML com estilos simples.
import pandas as pd


def df_to_html(df: pd.DataFrame, max_rows: int = 200) -> str:
    if df is None:
        return "<i>Sem dados</i>"
    if len(df) > max_rows:
        df = df.head(max_rows)
    return (
        df.to_html(
            border=0,
            classes="table table-sm",
            justify="center",
            index=True,
            float_format=lambda x: f"{x:.6g}"
        )
    )

def stylize(df: pd.DataFrame, max_rows: int = 200):
    """Retorna um Pandas Styler para ficar bonito no st.dataframe.
       - corta linhas se for muito grande
       - formata números com 4 casas
       - aplica um leve background_gradient
    """
    if df is None:
        return pd.DataFrame({"info": ["Sem dados"]}).style
    if len(df) > max_rows:
        df = df.head(max_rows)
    return (
        df.style
          .format(precision=4)
          .background_gradient(axis=None)
    )