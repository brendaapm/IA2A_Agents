
import io
import streamlit as st
from dotenv import load_dotenv

from app.agent.docs_agent import ask_docs_agent, file_to_images

load_dotenv()

st.set_page_config(page_title="CRM-IA – Agente de Documentos Fiscais", layout="wide")
st.title("CRM-IA – Agente Inteligente para Documentos Fiscais (OCR + GPT-4 + Validação)")

st.markdown(
    """
    Este aplicativo permite enviar um **PDF ou imagem de documento fiscal** (DANFE, DACTE, NFS-e),
    e utiliza um **agente baseado em GPT-4 com tools** para:

    - Fazer OCR do arquivo
    - Extrair campos estruturados (CNPJs, chave de acesso, data, valor total)
    - Validar os campos e calcular um score de confiança
    - Opcionalmente, salvar os dados em um banco SQLite

    Para isso, é necessário ter a variável de ambiente `OPENAI_API_KEY` configurada.
    """
)

uploaded = st.file_uploader(
    "Envie um arquivo de documento fiscal (PDF, JPG, JPEG, PNG)",
    type=["pdf", "jpg", "jpeg", "png"],
)

default_question = "Extraia e valide os campos principais dessa nota fiscal. Se estiver tudo ok, salve no banco."
user_message = st.text_input("Mensagem para o agente", value=default_question)

if uploaded is not None:
    file_bytes = uploaded.read()
    file_type = uploaded.name.split(".")[-1].lower()

    st.info(f"Arquivo recebido: **{uploaded.name}** ({file_type})")

    # Pré-visualização simples da primeira página/Imagem
    try:
        images = file_to_images(file_bytes, file_type)
        buf = io.BytesIO()
        images[0].save(buf, format="PNG")
        buf.seek(0)
        st.image(buf, caption="Pré-visualização da primeira página", use_column_width=True)
    except Exception as e:
        st.warning(f"Não foi possível gerar pré-visualização: {e}")

    if st.button("Executar agente (GPT-4 + tools)"):
        with st.spinner("Rodando agente de documentos fiscais..."):
            result = ask_docs_agent(file_bytes=file_bytes, file_type=file_type, user_message=user_message)

        st.markdown("## Resposta do agente")
        st.write(result.get("assistant_message", ""))

        if result.get("text_ocr"):
            with st.expander("Ver texto OCR bruto"):
                st.text_area("Texto OCR", value=result["text_ocr"], height=200)

        if result.get("fields"):
            st.markdown("### Campos extraídos / normalizados")
            st.json(result["fields"])

        if result.get("validation_report"):
            st.markdown("### Relatório de validação")
            st.json(result["validation_report"])

        if result.get("save_result"):
            st.markdown("### Resultado da persistência")
            st.json(result["save_result"])
else:
    st.info("Envie um arquivo para começar.")
