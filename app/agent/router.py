# app/agent/router.py
# Integração com OpenAI (tool calling) + execução das ferramentas.
# Versão com: schema_info, compute_stat, class_balance, groupby robusto e narrativa opcional.

import os
import json
from typing import Dict, Any

import pandas as pd
from openai import OpenAI

from .tools_spec import TOOLS
from app.tools.tables import stylize
from app.tools.plots import plot_histogram, plot_corr_heatmap

# -----------------------------------------------------------------------------
# Implementações das ferramentas
# -----------------------------------------------------------------------------

def _tool_describe_data(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    shape = df.shape
    dtypes = df.dtypes.astype(str).to_dict()
    nulls = df.isna().sum().to_dict()
    # compatível com pandas sem datetime_is_numeric
    try:
        desc = df.describe(include="all", datetime_is_numeric=True).transpose()
    except TypeError:
        desc = df.describe(include="all").transpose()
    return {
        "text": f"Shape: {shape[0]} linhas x {shape[1]} colunas\n\nTipos: {dtypes}\n\nNulls: {nulls}",
        "tables": [stylize(desc)]
    }


def _tool_schema_info(df: pd.DataFrame, show_examples: bool = False) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    num_cols = df.select_dtypes(include=["number"]).columns.tolist()
    cat_cols = [c for c in df.columns if c not in num_cols]
    out = pd.DataFrame({
        "column": num_cols + cat_cols,
        "type":   ["numeric"] * len(num_cols) + ["categorical"] * len(cat_cols)
    })
    extra = ""
    if show_examples and len(cat_cols) > 0:
        ex = {}
        for c in cat_cols[:10]:
            ex[c] = list(map(lambda x: str(x), pd.Series(df[c]).dropna().unique()[:5]))
        extra = f"\nExemplos (categorias – até 5 por coluna): {ex}"
    return {"tables": [stylize(out)], "text": extra.strip()}


def _tool_value_counts(df: pd.DataFrame, column: str, top: int = 20, plot: bool = True) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    if column not in df.columns:
        return {"text": f"Coluna '{column}' não encontrada."}
    vc = df[column].value_counts(dropna=False).head(top)
    result = {
        "text": f"Top {min(top, len(vc))} valores em '{column}'.",
        "tables": [stylize(vc.to_frame(name="count"))],
    }
    return result


def _tool_histogram(df: pd.DataFrame, column: str, bins: int = 30, log_scale: bool = False) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    try:
        img = plot_histogram(df, column=column, bins=bins, log_scale=log_scale)
        return {"images": [img], "text": f"Histograma de '{column}' (bins={bins}, log={log_scale})."}
    except Exception as e:
        return {"text": f"Erro ao plotar histograma: {e}"}


def _tool_corr_matrix(df: pd.DataFrame, method: str = "pearson") -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    try:
        img = plot_corr_heatmap(df, method=method)
        return {"images": [img], "text": f"Matriz de correlação ({method})."}
    except Exception as e:
        return {"text": f"Erro ao calcular correlação: {e}"}


def _tool_groupby_aggregate(
    df: pd.DataFrame,
    by=None,
    aggregations=None,
    columns=None,
    stats=None,
    sort_by=None,
    ascending=True,
    limit=50,
    __prompt: str = ""
) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    try:
        # montar aggregations se veio columns+stats
        if not aggregations:
            aggregations = {}
            if columns and stats:
                for col in columns:
                    if col in df.columns:
                        aggregations[col] = stats if len(stats) > 1 else stats[0]

        # fallback a partir do prompt se ainda vazio
        if not aggregations:
            pl = (__prompt or "").lower()
            mentioned_cols = [c for c in df.columns if c.lower() in pl]
            want_mean = ("mean" in pl) or ("média" in pl) or ("media" in pl)
            want_std  = ("std" in pl) or ("desvio" in pl)
            want_med  = ("median" in pl) or ("mediana" in pl)
            want_sum  = "sum" in pl
            want_cnt  = ("count" in pl) or ("contagem" in pl) or ("contar" in pl)
            want_min  = "min" in pl
            want_max  = "max" in pl
            metrics = []
            if want_mean: metrics.append("mean")
            if want_std:  metrics.append("std")
            if want_med:  metrics.append("median")
            if want_sum:  metrics.append("sum")
            if want_cnt:  metrics.append("count")
            if want_min:  metrics.append("min")
            if want_max:  metrics.append("max")
            if mentioned_cols and metrics:
                for col in mentioned_cols:
                    if col in df.columns and df[col].dtype.kind in "ifb":
                        aggregations[col] = metrics if len(metrics) > 1 else metrics[0]

        # fallback final
        if not aggregations:
            num_cols = df.select_dtypes(include=["number"]).columns.tolist()
            if not num_cols:
                return {"text": "Não há colunas numéricas para agregação."}
            aggregations = {num_cols[0]: "mean"}

        # SEM groupby: agrega no dataset inteiro
        if by is None or (isinstance(by, list) and len(by) == 0):
            aggregated = df.agg(aggregations)
            if isinstance(aggregated, pd.Series):
                aggregated = aggregated.to_frame().T
            return {"tables": [stylize(aggregated)]}

        # COM groupby
        grouped = df.groupby(by).agg(aggregations)
        # sort opcional (melhor esforço)
        if sort_by is not None:
            try:
                grouped = grouped.sort_values(by=sort_by, ascending=ascending)
            except Exception:
                pass
        if isinstance(limit, int) and limit > 0:
            grouped = grouped.head(limit)
        return {"tables": [stylize(grouped)]}
    except Exception as e:
        return {"text": f"Erro no groupby: {e}"}


def _tool_store_conclusions(mem, text: str) -> Dict[str, Any]:
    try:
        mem.add(text)
        return {"text": "Conclusão armazenada."}
    except Exception as e:
        return {"text": f"Falha ao armazenar conclusão: {e}"}


def _tool_get_conclusions(mem) -> Dict[str, Any]:
    return {"text": mem.get_all_as_markdown()}


def _tool_compute_stat(df: pd.DataFrame, column: str, stat: str) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    if column not in df.columns:
        return {"text": f"Coluna '{column}' não encontrada."}
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    value = getattr(s, stat)() if stat != "count" else s.count()
    return {"text": f"{stat}({column}) = {value:.6g}"}


def _tool_class_balance(df: pd.DataFrame, target: str = "Class", normalize: bool = True, top: int = 20) -> Dict[str, Any]:
    if df is None:
        return {"text": "Nenhum CSV carregado."}
    if target not in df.columns:
        return {"text": f"Coluna alvo '{target}' não encontrada."}
    counts = df[target].value_counts(dropna=False)
    props = df[target].value_counts(dropna=False, normalize=True)
    out = pd.DataFrame({"count": counts, "proportion": props}).head(top)
    txt = f"Balanceamento de '{target}': {len(counts)} classes. Classe minoritária ≈ {props.min():.4f}."
    return {"text": txt, "tables": [stylize(out)]}

# -----------------------------------------------------------------------------
# Chamada do modelo
# -----------------------------------------------------------------------------

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def ask_agent(prompt: str, df: pd.DataFrame, mem, concise: bool = True) -> Dict[str, Any]:
    """
    2 fases:
      1) modelo decide tools e obtem números/figuras;
      2) narrativa qualitativa (insights/limitações/próximos passos) SEM tools (apenas se houver material).
    """
    system = (
        "Você é um agente de EDA. SEMPRE use ferramentas para obter números e figuras; "
        "só depois escreva a análise qualitativa. Em cada resposta, siga esta ordem:\n"
        "1) Resultados objetivos (provenientes das ferramentas);\n"
        "2) Insights: interpretação do que os números sugerem;\n"
        "3) Limitações/cautelas (ex.: amostragem, outliers, correlação≠causalidade, data leakage);\n"
        "4) Próximos passos (2–3 sugestões práticas de análise/modelagem);\n"
        "Quando detectar achado importante (ex.: classe minoritária < 1%, correlações fortes, forte assimetria), "
        "inclua no FINAL da resposta uma linha exatamente no formato: Conclusão salva: \"<texto conciso>\".\n"
        "NÃO chame 'describe_data' a menos que o usuário peça explicitamente por 'resumo/describe/overview/sumário/shape/estatísticas'. "
        "Se a pergunta for sobre tipos (numérico vs categórico), use 'schema_info'."
    )

    client = _get_client()

    # 1ª chamada: o modelo decide quais ferramentas usar
    msg = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        tools=TOOLS,
        tool_choice="auto",
        temperature=0.2,
    )

    result: Dict[str, Any] = {"text": "", "tables": [], "images": []}

    tool_calls = msg.choices[0].message.tool_calls or []
    if not tool_calls:
        # Nenhuma ferramenta chamada: oriente o usuário a ser mais específico
        result["text"] = (
            "O agente não chamou ferramentas. Especifique a coluna/ação, por exemplo: "
            "'Quais são os tipos de dados?' (schema_info), "
            "'Qual é o balanceamento da coluna Class?' (class_balance), "
            "ou 'Faça um histograma de Amount' (histogram)."
        )
        return result

    for tc in tool_calls:
        name = tc.function.name
        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}

        if name == "describe_data":
            out = _tool_describe_data(df)
        elif name == "schema_info":
            out = _tool_schema_info(df, **args)
        elif name == "value_counts":
            out = _tool_value_counts(df, **args)
        elif name == "histogram":
            out = _tool_histogram(df, **args)
        elif name == "corr_matrix":
            out = _tool_corr_matrix(df, **args)
        elif name == "groupby_aggregate":
            out = _tool_groupby_aggregate(df, __prompt=prompt, **args)
        elif name == "store_conclusions":
            out = _tool_store_conclusions(mem, **args)
        elif name == "get_conclusions":
            out = _tool_get_conclusions(mem)
        elif name == "compute_stat":
            out = _tool_compute_stat(df, **args)
        elif name == "class_balance":
            out = _tool_class_balance(df, **args)
        else:
            out = {"text": f"Ferramenta desconhecida: {name}"}

        if out.get("text"):
            result["text"] += out["text"] + "\n\n"
        result["tables"] += out.get("tables", [])
        result["images"] += out.get("images", [])

    # 2ª chamada: narrativa qualitativa (sem tools).
    # Só fazemos se houve algum texto factual (para não "sujar" respostas que são só tabelas/figuras).
    tool_summary = result.get("text", "").strip()
    if concise or not tool_summary:
        return result

    try:
        msg_final = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "Resultados das ferramentas (resumo factual, não invente números):\n" + tool_summary}
            ],
            temperature=0.2,
        )
        narrative = msg_final.choices[0].message.content or ""
        if narrative:
            result["text"] = (tool_summary + "\n\n" + narrative).strip()
    except Exception:
        pass

    # Auto-salvar se houver sugestão explícita
    txt = result.get("text", "")
    if "Conclusão salva:" in txt:
        try:
            start = txt.index('Conclusão salva:') + len('Conclusão salva:')
            snippet = txt[start:].strip()
            # tira aspas se vierem "..."
            if snippet.startswith('"') and '"' in snippet[1:]:
                snippet = snippet[1:snippet.index('"', 1)]
            if snippet:
                _ = _tool_store_conclusions(mem, text=snippet)
        except Exception:
            pass

    return result