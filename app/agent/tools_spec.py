# JSON schemas das tools
# app/agent/tools_spec.py
# Define os JSON Schemas das ferramentas que o modelo pode chamar.

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "describe_data",
            "description": "Descreve o dataset carregado: shape, dtypes, nulls e estatísticas numéricas básicas.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "value_counts",
            "description": "Retorna value counts de uma coluna e opcionalmente desenha um barplot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "top": {"type": "integer", "default": 20, "minimum": 1},
                    "plot": {"type": "boolean", "default": True}
                },
                "required": ["column"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "histogram",
            "description": "Plota histograma de uma coluna numérica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "bins": {"type": "integer", "default": 30, "minimum": 1},
                    "log_scale": {"type": "boolean", "default": False}
                },
                "required": ["column"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "corr_matrix",
            "description": "Calcula matriz de correlação e desenha um heatmap simples.",
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["pearson", "spearman"], "default": "pearson"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "groupby_aggregate",
            "description": "Agrupa por colunas e aplica agregações. Pode receber 'aggregations' diretamente OU 'columns' + 'stats' (ex.: columns=['Amount'], stats=['mean','std']). Se 'by' não for passado, aplica agregações no dataset inteiro (sem groupby).",
            "parameters": {
                "type": "object",
                "properties": {
                    "by": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1
                    },
                    "aggregations": {
                        "type": "object",
                        "additionalProperties": {"type": "string"}
                    },
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "stats": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["mean","std","sum","count","min","max","median"]}
                    },
                    "sort_by": {"type": "string"},
                    "ascending": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 50, "minimum": 1}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "store_conclusions",
            "description": "Armazena uma conclusão textual relevante sobre o dataset.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_conclusions",
            "description": "Recupera conclusões salvas até o momento.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compute_stat",
            "description": "Calcula uma estatística simples (mean, median, std, min, max, count) para uma coluna.",
            "parameters": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "stat": {"type": "string", "enum": ["mean","median","std","min","max","count"]}
                },
                "required": ["column","stat"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schema_info",
            "description": "Lista colunas numéricas e categóricas do dataset (apenas tipos, sem estatísticas).",
            "parameters": {
                "type": "object",
                "properties": {
                    "show_examples": {"type": "boolean", "default": False}
                },
                "required": []
            }
        }
    },
]