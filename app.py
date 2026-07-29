import concurrent.futures
from datetime import datetime
import io
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(
    page_title="Stock Screener - Minervini & Weinstein", layout="wide"
)

st.markdown(
    "# 📈 Stock Screener Pro: Criterios Minervini & Weinstein (Universo"
    " Completo)"
)

with st.expander("📖 ¿En qué consisten los filtros metodológicos?"):
  st.markdown("""
    * **Mark Minervini (Trend Template):** Busca acciones en supertendencia alcista comprobando que el precio esté por encima de las medias móviles (50, 150 y 200 días), que la media de 150 supere a la de 200, y que la cotización esté cerca de sus máximos anuales.
    * **Stan Weinstein (Estadios):** Identifica el **Estadio 2 (Avance)**, validando que el precio cotice fuerte por encima de la media de referencia a mediano/largo plazo orientada al alza.
    """)


@st.cache_data(ttl=3600)
def load_and_analyze_market():
  tickers = set()
  headers = {"User-Agent": "Mozilla/5.0"}

  try:
    url_sp = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response = requests.get(url_sp, headers=headers)
    df_sp = pd.read_html(io.StringIO(response.text))[0]
    tickers.update(
        df_sp["Symbol"].str.replace(".", "-", regex=False).tolist()
    )
  except Exception:
    pass

  try:
    url_nq = (
        "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/csv/nasdaq_tickers.csv"
    )
    response_nq = requests.get(url_nq, headers=headers)
    df_nq = pd.read_csv(io.StringIO(response_nq.text))
    col = "Ticker" if "Ticker" in df_nq.columns else "Symbol"
    nasdaq_list = (
        df_nq[col]
        .dropna()
        .astype(str)
        .str.replace(".", "-", regex=False)
        .tolist()
    )
    nasdaq_list = [t for t in nasdaq_list if len(t) <= 5 and "/" not in t]
    tickers.update(nasdaq_list)
  except Exception:
    pass

  universe = sorted(list(tickers))
  results = []

  def process_ticker(ticker):
    try:
      df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
      if df.empty or len(df) < 200:
        return None

      if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

      close = df["Close"]
      current_price = float(close.iloc[-1])
      volume = float(df["Volume"].iloc[-1])

      sma_50 = float(close.rolling(window=50).mean().iloc[-1])
      sma_150 = float(close.rolling(window=150).mean().iloc[-1])
      sma_200 = float(close.rolling(window=200).mean().iloc[-1])

      low_52w = float(close.min())
      high_52w = float(close.max())

      minervini_check = (
          (current_price > sma_50)
          and (current_price > sma_150)
          and (current_price > sma_200)
          and (sma_150 > sma_200)
          and (current_price >= low_52w * 1.30)
          and (current_price >= high_52w * 0.75)
      )

      weinstein_stage_2 = (current_price > sma_150) and (
          current_price > high_52w * 0.70
      )
      signal = "BUY" if (minervini_check and weinstein_stage_2) else "NEUTRAL"

      return {
          "Ticker": ticker,
          "Precio": round(current_price, 2),
          "Volumen": int(volume),
          "SMA_50": round(sma_50, 2),
          "SMA_200": round(sma_200, 2),
          "Minervini_Pass": minervini_check,
          "Weinstein_Stage2": weinstein_stage_2,
          "Signal": signal,
      }
    except Exception:
      return None

  with concurrent.futures.ThreadPoolExecutor(max_workers=40) as executor:
    futures = {executor.submit(process_ticker, t): t for t in universe}
    for future in concurrent.futures.as_completed(futures):
      res = future.result()
      if res:
        results.append(res)

  return pd.DataFrame(results)


with st.spinner(
    "Analizando el mercado en tiempo real (aplicando filtros metodológicos)..."
):
  df_market = load_and_analyze_market()

if df_market.empty:
  st.error("No se pudieron cargar los datos del mercado.")
else:
  st.success(f"¡Análisis completado! Empresas procesadas: {len(df_market):,}")

  c1, c2, c3 = st.columns(3)
  c1.metric(
      "Aprobados Minervini",
      len(df_market[df_market["Minervini_Pass"] == True]),
  )
  c2.metric(
      "En Estadio 2 (Weinstein)",
      len(df_market[df_market["Weinstein_Stage2"] == True]),
  )
  c3.metric(
      "Señales Fuertes (BUY)", len(df_market[df_market["Signal"] == "BUY"])
  )

  st.markdown("---")
  st.markdown("### 📊 Listado Completo y Filtros")

  only_approved = st.checkbox(
      "Mostrar únicamente empresas que cumplen AMBOS criterios (Minervini +"
      " Weinstein)"
  )
  display_df = (
      df_market[df_market["Signal"] == "BUY"] if only_approved else df_market
  )

  st.dataframe(display_df, use_container_width=True, hide_index=True)

  st.markdown("---")
  st.markdown(
      "### 📉 Gráficos Interactivos con Medias Móviles Clave (50 y 200 días)"
  )

  selected_ticker = st.selectbox(
      "Selecciona una empresa del universo para visualizar su gráfico técnico:",
      df_market["Ticker"].tolist(),
  )

  if selected_ticker:
    with st.spinner(f"Generando gráfico para {selected_ticker}..."):
      hist_df = yf.download(
          selected_ticker, period="1y", progress=False, auto_adjust=True
      )
      if isinstance(hist_df.columns, pd.MultiIndex):
        hist_df.columns = hist_df.columns.get_level_values(0)

      hist_df["SMA_50"] = hist_df["Close"].rolling(window=50).mean()
      hist_df["SMA_200"] = hist_df["Close"].rolling(window=200).mean()

      row_data = df_market[df_market["Ticker"] == selected_ticker].iloc[0]

      fig = go.Figure()
      fig.add_trace(
          go.Scatter(
              x=hist_df.index,
              y=hist_df["Close"],
              name="Precio Cierre",
              line=dict(color="white", width=1.5),
          )
      )
      fig.add_trace(
          go.Scatter(
              x=hist_df.index,
              y=hist_df["SMA_50"],
              name="SMA 50 (Minervini)",
              line=dict(color="orange", width=1.2),
          )
      )
      fig.add_trace(
          go.Scatter(
              x=hist_df.index,
              y=hist_df["SMA_200"],
              name="SMA 200 (Tendencia)",
              line=dict(color="red", width=1.2),
          )
      )

      fig.update_layout(
          title=(
              f"Análisis Técnico: {selected_ticker} | Minervini:"
              f" {row_data['Minervini_Pass']} | Weinstein Estadio 2:"
              f" {row_data['Weinstein_Stage2']}"
          ),
          xaxis_title="Fecha",
          yaxis_title="Precio ($)",
          template="plotly_dark",
          height=550,
      )

      st.plotly_chart(fig, use_container_width=True)00
