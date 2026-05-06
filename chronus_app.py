import streamlit as st
import pdfplumber
import pandas as pd
import requests
import re
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")

# =========================================
# STATE
# =========================================
if "pilotos" not in st.session_state:
    st.session_state.pilotos = None

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
# DOWNLOAD
# =========================================
def baixar_pdf(url):
    pdf_url = url.replace("/show", "/download")
    r = requests.get(pdf_url)

    if r.status_code != 200:
        raise Exception("Link inválido ou indisponível")

    with open("resultado.pdf", "wb") as f:
        f.write(r.content)

    return "resultado.pdf"

# =========================================
# EXTRAÇÃO
# =========================================
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
# ESTILO (CORES)
# =========================================
def estilizar(df):
    def cor(val):
        try:
            v = float(val.replace("s", ""))
            if v < 0:
                return "color: green; font-weight: bold"
            elif v > 0:
                return "color: red; font-weight: bold"
        except:
            return ""
    return df.style.map(cor, subset=["Diferença"])

# =========================================
# VENCEDOR
# =========================================
def detectar_vencedor(df, nome_a, nome_b):
    total = df[df["Especial"] == "TOTAL"]

    if total.empty:
        return "Não definido"

    diff = total["Dif(s)"].values[0]

    if diff < 0:
        return nome_a
    elif diff > 0:
        return nome_b
    else:
        return "Empate"

# =========================================
# UI
# =========================================
st.title("🏁 Comparador de Pilotos - Chronus")

url = st.text_input(
    "Cole o link dos resultados referente à Performance Pilotos PDF"
)

if st.button("🔄 Carregar dados"):
    try:
        with st.spinner("Baixando e processando..."):
            pdf_path = baixar_pdf(url)
            pilotos = extrair_dados_pdf(pdf_path)

            if not pilotos:
                st.error("Nenhum piloto encontrado neste arquivo")
            else:
                st.session_state.pilotos = pilotos
                st.success(f"{len(pilotos)} pilotos carregados")

    except Exception as e:
        st.session_state.pilotos = None
        st.error(f"Erro ao carregar dados: {e}")

# =========================================
# SELEÇÃO
# =========================================
if st.session_state.pilotos:

    nomes = list(st.session_state.pilotos.keys())

    col1, col2 = st.columns(2)

    with col1:
        piloto_a = st.selectbox(
            "Piloto A",
            [""] + nomes,
            index=0
        )

    with col2:
        piloto_b = st.selectbox(
            "Piloto B",
            [""] + nomes,
            index=0
        )

    # validações
    if piloto_a and piloto_b:

        if piloto_a == piloto_b:
            st.warning("Não é possível comparar o mesmo piloto")
        else:
            df = comparar(
                st.session_state.pilotos[piloto_a],
                st.session_state.pilotos[piloto_b]
            )

            vencedor = detectar_vencedor(df, piloto_a, piloto_b)

            st.subheader(f"🏆 Vencedor: {vencedor}")

            st.dataframe(
                estilizar(df[[
                    "Especial",
                    "Tempo A",
                    "Diferença",
                    "Tempo B"
                ]]).hide(axis="index"),
                use_container_width=True
            )

            # gráfico
            # gráfico (ignorando V1)
            df_plot = df[
                (df["Especial"] != "TOTAL") &
                (~df["Especial"].str.startswith("V1"))
            ]
            
            fig, ax = plt.subplots()
            ax.plot(df_plot["Especial"], df_plot["Acumulado"], marker='o')
            
            ax.set_title("Ganho/Perda Acumulado (sem V1)")
            ax.set_xlabel("Especial")
            ax.set_ylabel("Diferença (s)")
            
            plt.xticks(rotation=45)
            plt.grid()
            
            st.pyplot(fig)

            st.markdown("""
### 📊 COMO INTERPRETAR O GRÁFICO

- **Linha subindo → Piloto A perdendo tempo**
- **Linha descendo → Piloto A ganhando tempo**
- **Linha plana → tempos equivalentes**
""")
