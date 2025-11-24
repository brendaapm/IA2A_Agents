
import io
import json
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PIL import Image
from pdf2image import convert_from_bytes
import pytesseract
from openai import OpenAI

client = OpenAI()


# ============================================================
# 1. Ingestão & Pré-processamento + OCR
# ============================================================

def file_to_images(file_bytes: bytes, file_type: str) -> List[Image.Image]:
    """
    Converte um arquivo PDF ou imagem em uma lista de imagens PIL.
    file_type: extensão do arquivo, ex: "pdf", "jpg", "png".
    """
    ft = file_type.lower()
    if ft == "pdf":
        images = convert_from_bytes(file_bytes)
        return [img.convert("RGB") for img in images]
    elif ft in {"jpg", "jpeg", "png"}:
        img = Image.open(io.BytesIO(file_bytes))
        return [img.convert("RGB")]
    else:
        raise ValueError(f"Tipo de arquivo não suportado para OCR: {file_type}")


def run_ocr(images: List[Image.Image], lang: str = "por") -> str:
    """
    Roda OCR em uma lista de imagens e concatena o texto.
    """
    texts: List[str] = []
    for img in images:
        text = pytesseract.image_to_string(img, lang=lang)
        texts.append(text)
    return "\n\n".join(texts)


# ============================================================
# 2. Extração estruturada via GPT-4 (MLLM / LLM)
# ============================================================

INVOICE_EXTRACTION_PROMPT = """
Você é um especialista em documentos fiscais brasileiros.

A partir do TEXTO abaixo (que veio de OCR de DANFE/DACTE/NFS-e),
extraia os campos principais em formato JSON, seguindo exatamente esta estrutura de chaves:

{
  "tipo_documento": "DANFE | DACTE | NFS-e | desconhecido",
  "chave_acesso": "<string ou null>",
  "cnpj_emitente": "<string ou null>",
  "razao_social_emitente": "<string ou null>",
  "cnpj_destinatario": "<string ou null>",
  "razao_social_destinatario": "<string ou null>",
  "data_emissao": "<string no formato DD/MM/AAAA ou null>",
  "valor_total": "<número em formato string, ex: 1234.56, ou null>"
}

Regras:
- Se não encontrar algum campo, use null.
- Não escreva nenhuma explicação fora do JSON.
- Não inclua comentários.
- Se tiver dúvida entre dois valores, escolha o mais plausível com base no contexto.
- Não invente campos que não existam no texto.

TEXTO OCR:
----------------
{texto_ocr}
----------------
"""


def extract_invoice_fields(text_ocr: str, model: str = "gpt-4.1") -> Dict[str, Any]:
    """
    Usa GPT-4 para transformar texto OCR em JSON com campos fiscais.
    """
    prompt = INVOICE_EXTRACTION_PROMPT.format(texto_ocr=text_ocr[:6000])

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "Você responde SOMENTE um JSON válido, sem nenhum texto fora do JSON."
            },
            {
                "role": "user",
                "content": prompt
            },
        ],
        temperature=0.1,
    )

    content = response.choices[0].message.content or "{}"

    try:
        data = json.loads(content)
    except Exception:
        data = {"raw_response": content}

    return data


# ============================================================
# 3. Validação textual dos campos extraídos
# ============================================================

def _only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _validate_cnpj(cnpj: str) -> bool:
    digits = _only_digits(cnpj)
    return len(digits) == 14  # checagem simples; pode ser expandida p/ dígito verificador


def _validate_chave(chave: str) -> bool:
    digits = _only_digits(chave)
    return len(digits) == 44


def _validate_date(date_str: str) -> bool:
    if not date_str:
        return False
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            datetime.strptime(date_str, fmt)
            return True
        except Exception:
            continue
    return False


def _validate_valor(valor_str: str) -> bool:
    if not valor_str:
        return False
    vs = valor_str.replace(".", "").replace(",", ".")
    try:
        float(vs)
        return True
    except Exception:
        return False


def validate_invoice_fields(fields: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Valida os campos extraídos e devolve:
      - fields_normalized: campos possivelmente normalizados
      - report: dicionário com flags, score e mensagens
    """
    fields = dict(fields or {})

    report: Dict[str, Any] = {
        "cnpj_emitente_valido": _validate_cnpj(fields.get("cnpj_emitente", "")),
        "cnpj_destinatario_valido": _validate_cnpj(fields.get("cnpj_destinatario", "")),
        "chave_valida": _validate_chave(fields.get("chave_acesso", "")),
        "data_emissao_valida": _validate_date(fields.get("data_emissao", "")),
        "valor_total_valido": _validate_valor(fields.get("valor_total", "")),
        "campos_suspeitos": [],
        "score_confianca": 1.0,
    }

    for key, ok in [
        ("cnpj_emitente", report["cnpj_emitente_valido"]),
        ("cnpj_destinatario", report["cnpj_destinatario_valido"]),
        ("chave_acesso", report["chave_valida"]),
        ("data_emissao", report["data_emissao_valida"]),
        ("valor_total", report["valor_total_valido"]),
    ]:
        if not ok:
            report["campos_suspeitos"].append(key)

    n_sus = len(report["campos_suspeitos"])
    if n_sus == 0:
        report["score_confianca"] = 1.0
    elif n_sus <= 2:
        report["score_confianca"] = 0.7
    else:
        report["score_confianca"] = 0.4

    return fields, report


# ============================================================
# 4. Persistência em SQLite
# ============================================================

def _get_db_connection(db_path: str = "invoices.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            fields_json TEXT NOT NULL,
            validation_report_json TEXT NOT NULL
        )
        """
    )
    return conn


def save_invoice_to_db(
    fields: Dict[str, Any],
    validation_report: Dict[str, Any],
    db_path: str = "invoices.db",
) -> Dict[str, Any]:
    """
    Salva os campos e o relatório de validação em um banco SQLite.
    Retorna um dicionário com status e id do registro.
    """
    conn = _get_db_connection(db_path)
    try:
        created_at = datetime.utcnow().isoformat()
        fields_json = json.dumps(fields, ensure_ascii=False)
        validation_json = json.dumps(validation_report, ensure_ascii=False)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO invoices (created_at, fields_json, validation_report_json) VALUES (?, ?, ?)",
            (created_at, fields_json, validation_json),
        )
        conn.commit()
        invoice_id = cur.lastrowid
    finally:
        conn.close()

    return {"status": "ok", "id": invoice_id, "created_at": created_at}


# ============================================================
# 5. Definição das tools (run_ocr, extract, validate, save)
# ============================================================

TOOLS_DOCS = [
    {
        "type": "function",
        "function": {
            "name": "run_ocr",
            "description": (
                "Executa OCR no arquivo de documento fiscal enviado (PDF ou imagem) "
                "e retorna o texto bruto extraído."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "lang": {
                        "type": "string",
                        "description": "Idioma para OCR (padrão: 'por').",
                        "default": "por",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_invoice_fields",
            "description": (
                "Extrai campos estruturados (tipo_documento, chave_acesso, CNPJs, data_emissao, "
                "valor_total etc.) a partir do texto OCR de um documento fiscal brasileiro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text_ocr": {
                        "type": "string",
                        "description": "Texto bruto de OCR da DANFE/DACTE/NFS-e.",
                    }
                },
                "required": ["text_ocr"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_invoice_fields",
            "description": (
                "Valida e normaliza os campos extraídos de um documento fiscal, "
                "retornando um relatório de validação com score de confiança e campos suspeitos."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "description": (
                            "Objeto JSON com os campos da nota fiscal, "
                            "como retornado por extract_invoice_fields."
                        ),
                    }
                },
                "required": ["fields"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_invoice_to_db",
            "description": (
                "Persiste os campos de nota fiscal e o relatório de validação em um banco SQLite, "
                "retornando o ID do registro criado."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fields": {
                        "type": "object",
                        "description": "Campos da nota fiscal a serem salvos.",
                    },
                    "validation_report": {
                        "type": "object",
                        "description": "Relatório de validação associado.",
                    },
                },
                "required": ["fields", "validation_report"],
            },
        },
    },
]


# ============================================================
# 6. System prompt enriquecido e agente tool-based
# ============================================================

SYSTEM_PROMPT_DOCS = """
Você é um agente especialista em documentos fiscais brasileiros (DANFE, DACTE, NFS-e).

Seu contexto:
- O usuário envia um ARQUIVO de documento fiscal (PDF de imagem ou foto).
- Você NÃO vê o arquivo diretamente: para ler o conteúdo, precisa chamar a tool `run_ocr`.
- A partir do texto OCR, você pode usar `extract_invoice_fields` para extrair os campos principais.
- Depois, você pode usar `validate_invoice_fields` para checar formato, consistência básica e gerar um score de confiança.
- Se fizer sentido, pode usar `save_invoice_to_db` para persistir os dados em um banco SQLite.

Objetivos principais:
1) Garantir que os campos sejam extraídos com o máximo de precisão possível.
2) Deixar claro para o usuário quais campos foram encontrados, quais estão suspeitos e qual o nível de confiança da extração.
3) Evitar alucinações: não inventar CNPJ, chave de acesso ou valores que não estejam respaldados pelo texto ou pelas tools.
4) Sempre que houver dúvida relevante, sinalizar a necessidade de revisão humana (HITL).

Estratégia recomendada:
- Primeiro, se você ainda não tiver o texto da nota, chame `run_ocr`.
- Em seguida, use `extract_invoice_fields` com o texto OCR.
- Depois, use `validate_invoice_fields` com o JSON de campos.
- Se o usuário pedir para salvar ou se o score for razoável e o contexto permitir, use `save_invoice_to_db`.
- Ao final, responda em linguagem natural, em português, explicando:
  * o que você fez (quais tools usou, de forma resumida),
  * os principais campos extraídos (CNPJ, chave, data, valor),
  * os campos suspeitos ou inválidos,
  * o score de confiança e se recomenda revisão humana.

Estilo de resposta:
- Seja direto, objetivo e transparente.
- Não exponha detalhes internos de implementação desnecessários (como caminhos de arquivo ou SQL cru).
- Quando fizer sentido, utilize listas e subtítulos para organizar a resposta.
"""


def ask_docs_agent(file_bytes: bytes, file_type: str, user_message: str) -> Dict[str, Any]:
    """
    Executa uma interação com o agente de documentos fiscais (GPT-4 + tools).

    Parâmetros:
    - file_bytes: conteúdo bruto do arquivo enviado (PDF/imagem).
    - file_type: extensão do arquivo, ex: "pdf", "jpg", "png".
    - user_message: pergunta ou instrução do usuário.

    Retorna um dicionário com:
      - "assistant_message": texto final de resposta do modelo
      - "text_ocr": texto OCR (se gerado)
      - "fields": campos extraídos/normalizados (se gerados)
      - "validation_report": relatório de validação (se gerado)
      - "save_result": resultado da persistência (se chamada)
    """
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT_DOCS},
        {
            "role": "user",
            "content": (
                "Um arquivo de documento fiscal foi enviado (PDF ou imagem). "
                "Use as tools disponíveis para fazer OCR, extrair e validar os campos, "
                "e salvar se fizer sentido.\n\n"
                f"Pedido do usuário: {user_message}"
            ),
        },
    ]

    text_ocr: str = ""
    fields_result: Dict[str, Any] = {}
    validation_result: Dict[str, Any] = {}
    save_result: Dict[str, Any] = {}

    def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal text_ocr, fields_result, validation_result, save_result

        if name == "run_ocr":
            lang = arguments.get("lang", "por")
            images = file_to_images(file_bytes, file_type)
            text = run_ocr(images, lang=lang)
            text_ocr = text
            return {"text_ocr": text}

        elif name == "extract_invoice_fields":
            txt = arguments.get("text_ocr") or text_ocr
            data = extract_invoice_fields(txt)
            fields_result = data
            return data

        elif name == "validate_invoice_fields":
            fields_arg = arguments.get("fields") or fields_result
            fields_norm, report = validate_invoice_fields(fields_arg)
            fields_result = fields_norm
            validation_result = report
            return {
                "fields_normalized": fields_norm,
                "validation_report": report,
            }

        elif name == "save_invoice_to_db":
            fields_arg = arguments.get("fields") or fields_result
            report_arg = arguments.get("validation_report") or validation_result
            res = save_invoice_to_db(fields_arg, report_arg)
            save_result = res
            return res

        else:
            raise ValueError(f"Tool desconhecida: {name}")

    # Loop simples para permitir múltiplas chamadas de tools
    for _ in range(6):
        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            tools=TOOLS_DOCS,
            tool_choice="auto",
            temperature=0.1,
        )

        choice = response.choices[0]
        msg = choice.message

        # Se não houver chamada de ferramenta, é a resposta final
        if not getattr(msg, "tool_calls", None):
            assistant_message = msg.content or ""
            return {
                "assistant_message": assistant_message,
                "text_ocr": text_ocr,
                "fields": fields_result,
                "validation_report": validation_result,
                "save_result": save_result,
            }

        # Executa as tools solicitadas
        messages.append({
            "role": "assistant",
            "tool_calls": msg.tool_calls,
        })

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            raw_args = tool_call.function.arguments or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}

            tool_output = _call_tool(tool_name, args)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(tool_output, ensure_ascii=False),
                }
            )

    # Fallback se sair do loop sem resposta final
    return {
        "assistant_message": "Não consegui chegar a uma resposta final após usar as ferramentas.",
        "text_ocr": text_ocr,
        "fields": fields_result,
        "validation_report": validation_result,
        "save_result": save_result,
    }
