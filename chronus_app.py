import streamlit as st
import pdfplumber
import pandas as pd
import requests
import re
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")

# =========================================
# UTIL
# =========================================
def limpar_nome(nome):
    return re.sub(r"\s+C$", "", nome.strip())

def tempo_para_segundos_hms(t):
    try:
        h, m, s = t.split(':')
        return int(h)*3600 + int(m)*60 + float(s)
    except:
        return None

# =========================================
# DOWNLOAD + CACHE
# =========================================
@st.cache_data
def baixar_pdf(url):
    pdf_url = url.replace("/show", "/download")
    r = requests.get(pdf_url)
    r.raise_for_status()

    with open("resultado.pdf", "wb") as f:
        f.write(r.content)

    return "resultado.pdf"

# =========================================
# EXTRAÇÃO
# =========================================
@st.cache_data
def extrair_dados_pdf(pdf_path):
    pilotos = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            texto = page.extract_text()
            if not texto:
                continue

            num_match = re.search(r"N[º°o]:?\s*(\d+)", texto)
            nome_match = re.search(r"Nome:\s*([A-ZÀ-Ÿ\s]+)", texto)

            if not num_match or not nome_match:
                continue

            numero = num_match.group(1).zfill(4)
            nome = limpar_nome(nome_match.group(1))
            piloto_nome = f"#{numero} - {nome}"

            linhas = texto.split("\n")

            bloco = []
            capturar = False

            for linha in linhas:
                if "Especial" in linha:
                    capturar = True
                if capturar:
                    bloco.append(linha)
                if capturar and linha.strip() == "":
                    break

            dados = []

            for linha in bloco:
                esp_match = re.search(r"(V\d+E\d+\s*Cheg)", linha)

                if esp_match:
                    especial = esp_match.group(1)
                    tempos = re.findall(r"\d{2}:\d{2}:\d{2}\.\d{3}", linha)

                    if tempos:
                        tempo = tempos[-1]

                        dados.append({
                            "Especial": especial,
                            "Tempo": tempo,
                            "Tempo_seg": tempo_para_segundos_hms(tempo)
                        })

            total_match = re.search(r"TEMPO:\s*(\d{2}:\d{2}:\d{2}\.\d{3})", texto)
            if total_match:
                dados.append({
                    "Especial": "TOTAL",
                    "Tempo": total_match.group(1),
                    "Tempo_seg": tempo_para_segundos_hms(total_match.group(1))
                })

            if dados:
                df = pd.DataFrame(dados)

                df["ordem"] = df["Especial"].apply(
                    lambda x: (999, 999) if x == "TOTAL"
                    else tuple(map(int, re.findall(r"\d+", x)))
                )

                df = df.sort_values("ordem").drop(columns="ordem")
                pilotos[piloto_nome] = df

    return pilotos

# =========================================
# COMPARAÇÃO
# =========================================
def comparar(df1, df2):
    merged = pd.merge(df1, df2, on="Especial", suffixes=(" A", " B"))

    merged["Dif(s)"] = merged["Tempo_seg A"] - merged["Tempo_seg B"]
    merged["Acumulado"] = merged["Dif(s)"].cumsum()

    def format_diff(x):
        return f"+{x:.2f}s" if x > 0 else f"{x:.2f}s"

    merged["Diferença"] = merged["Dif(s)"].apply(format_diff)

    return merged

# =========================================
# VENCEDOR
# =========================================
def detectar_vencedor(df, nome_a, nome_b):
    total = df[df["Especial"] == "TOTAL"]

    if total.empty:
        return "Não foi possível determinar"

    diff = total["Dif(s)"].values[0]

    if diff < 0:
        return f"🏆 {nome_a}"
    elif diff > 0:
        return f"🏆 {nome_b}"
    else:
        return "🤝 Empate"

# =========================================
# UI
# =========================================
st.title("🏁 Comparador de Pilotos - Chronus")

url = st.text_input(
    "Cole o link do evento Chronus",
    "https://chronusae.com.br/eventos/1140/file/3869/show"
)

if url:
    with st.spinner("Carregando dados..."):
        try:
            pdf_path = baixar_pdf(url)
            pilotos = extrair_dados_pdf(pdf_path)
        except Exception as e:
            st.error(f"Erro: {e}")
            st.stop()

    nomes = list(pilotos.keys())

    if not nomes:
        st.warning("Nenhum piloto encontrado")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        piloto_a = st.selectbox("Piloto A", nomes)

    with col2:
        piloto_b = st.selectbox("Piloto B", nomes)

    if piloto_a != piloto_b:
        df = comparar(pilotos[piloto_a], pilotos[piloto_b])

        vencedor = detectar_vencedor(df, piloto_a, piloto_b)

        st.subheader(f"🏆 Vencedor: {vencedor}")

        st.dataframe(
            df[["Especial", "Tempo A", "Diferença", "Tempo B"]],
            use_container_width=True
        )

        # GRÁFICO
        df_plot = df[df["Especial"] != "TOTAL"]

        fig, ax = plt.subplots()
        ax.plot(df_plot["Especial"], df_plot["Acumulado"], marker='o')
        ax.set_title("Ganho/Perda Acumulado")
        ax.set_xlabel("Especial")
        ax.set_ylabel("Diferença (s)")
        plt.xticks(rotation=45)

        st.pyplot(fig)