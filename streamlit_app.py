# app/streamlit_app.py
import os
import io
import base64
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Carrega variáveis do .env (OPENAI_API_KEY, OPENAI_MODEL, etc.)
load_dotenv()

from app.agent.router import ask_agent
from app.memory.memory_store import Memory

st.set_page_config(page_title="EDA Agent", layout="wide")
st.title("EDA Agent – CSV qualquer")

concise = st.sidebar.toggle("Modo conciso (ocultar narrativa)", value=False)

# ---------------------------------------------------------------------
# Estado da sessão
# ---------------------------------------------------------------------
session_state = st.session_state
if "df" not in session_state:
    session_state.df = None
if "mem" not in session_state:
    session_state.mem = Memory("mem.jsonl")  # persiste em arquivo, mas vamos limpar a cada upload
if "upload_sig" not in session_state:
    session_state.upload_sig = None

# ---------------------------------------------------------------------
# Upload de CSV (limpa memória quando o arquivo muda)
# ---------------------------------------------------------------------
uploaded = st.file_uploader("Faça upload de um CSV", type=["csv"])

if uploaded is not None:
    # assinatura simples (nome + tamanho) para detectar troca de arquivo
    sig = (uploaded.name, uploaded.size)
    if session_state.upload_sig != sig:
        session_state.upload_sig = sig
        # reposiciona o ponteiro antes de ler
        uploaded.seek(0)
        try:
            session_state.df = pd.read_csv(uploaded)
            # limpa a memória ao trocar de CSV
            session_state.mem.clear()
            st.success(
                f"CSV carregado: {session_state.df.shape[0]} linhas, "
                f"{session_state.df.shape[1]} colunas. Memória da sessão foi reiniciada."
            )
        except Exception as e:
            st.error(f"Erro ao ler CSV: {e}")

# ---------------------------------------------------------------------
# Caixa de pergunta e execução do agente
# ---------------------------------------------------------------------
prompt = st.text_input("Pergunte algo sobre os dados")
if st.button("Enviar", disabled=session_state.df is None or not prompt):
    with st.spinner("Analisando com o agente..."):
        result = ask_agent(prompt, df=session_state.df, mem=session_state.mem, concise=concise)
        # Texto (insights/resultados factuais)
        if result.get("text"):
            st.markdown(result["text"])
        # Tabelas (DataFrame ou Styler)
        for tbl in result.get("tables", []):
            st.dataframe(tbl, use_container_width=True, height=400)
        # Imagens (PNG base64)
        for img_b64 in result.get("images", []):
            st.image(io.BytesIO(base64.b64decode(img_b64)))

# ---------------------------------------------------------------------
# Conclusões (memória da sessão)
# ---------------------------------------------------------------------
with st.expander("Conclusões do agente"):
    st.markdown(session_state.mem.get_all_as_markdown())

# ---------------------------------------------------------------------
# Rodapé opcional: status da API
# ---------------------------------------------------------------------
with st.sidebar:
    st.caption("⚙️ Configuração")
    st.write("Modelo:", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    st.write("Chave carregada:", "✅" if os.getenv("OPENAI_API_KEY") else "❌")