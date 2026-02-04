import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import urllib3
from io import StringIO
import time

# --- 0. 基礎設定 ---
st.set_page_config(page_title="台股價值大師雷達", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 介面標題 ---
st.title("📊 台股價值投資掃描器 (抗干擾增強版)")
st.markdown("""
**策略邏輯：** 尋找低本益比、低股價淨值比、高殖利率且具備護城河(ROE)的優質公司。
> *如果出現「找不到符合條件」，通常是 Yahoo Finance 暫時阻擋了連線。*
""")

# --- 2. 核心功能：獲取股票清單 ---
@st.cache_data(ttl=86400)
def get_tw_stock_list():
    status_placeholder = st.empty()
    status_placeholder.text("正在連線證交所抓取最新清單...")

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        def fetch_and_process(url, suffix):
            response = requests.get(url, verify=False, headers=headers)
            response.encoding = 'big5' 
            dfs = pd.read_html(StringIO(response.text))
            if not dfs: return pd.DataFrame()
            df = dfs[0]
            
            header_idx = -1
            for i in range(min(5, len(df))):
                row_str = str(df.iloc[i].values)
                if '有價證券代號' in row_str:
                    header_idx = i
                    break
            
            if header_idx == -1: return pd.DataFrame()

            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx+1:].copy()
            df = df.dropna(subset=['有價證券代號及名稱'])
            df = df[df['有價證券代號及名稱'].astype(str).str.contains('　')]
            df['code'] = df['有價證券代號及名稱'].str.split('　').str[0]
            df['name'] = df['有價證券代號及名稱'].str.split('　').str[1]
            df = df[df['code'].str.len() == 4]
            df['yf_ticker'] = df['code'] + suffix
            return df[['code', 'name', 'yf_ticker']]

        df_tw = fetch_and_process("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", ".TW")
        df_two = fetch_and_process("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", ".TWO")
        df_final = pd.concat([df_tw, df_two], ignore_index=True)
        
        if df_final.empty: raise Exception("抓取到的清單為空")

        status_placeholder.success(f"成功抓取 {len(df_final)} 檔股票！")
        return df_final

    except Exception as e:
        status_placeholder.warning(f"無法連線證交所 ({e})，切換至救援模式。")
        fallback_data = [
            {"code": "2330", "name": "台積電", "yf_ticker": "2330.TW"},
            {"code": "2317", "name": "鴻海", "yf_ticker": "2317.TW"},
            {"code": "2412", "name": "中華電", "yf_ticker": "2412.TW"},
            {"code": "2886", "name": "兆豐金", "yf_ticker": "2886.TW"},
            {"code": "1101", "name": "台泥", "yf_ticker": "1101.TW"},
        ]
        return pd.DataFrame(fallback_data)

df_stocks = get_tw_stock_list()

# --- 3. 側邊欄設定 ---
st.sidebar.header("⚙️ 1. 連線測試")
if st.sidebar.button("測試 Yahoo 連線 (台積電)"):
    try:
        test_stock = yf.Ticker("2330.TW")
        test_info = test_stock.info
        st.sidebar.json(test_info) # 顯示原始數據
        if 'currentPrice' in test_info or 'regularMarketPrice' in test_info:
            st.sidebar.success("連線成功！數據正常。")
        else:
            st.sidebar.error("連線成功但無數據 (可能被鎖 IP)。")
    except Exception as e:
        st.sidebar.error(f"連線失敗: {e}")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ 2. 篩選參數")
cr_pe = st.sidebar.number_input("最大本益比 (P/E)", value=25.0) # 放寬預設值
cr_pb = st.sidebar.number_input("最大股價淨值比 (P/B)", value=5.0)
cr_yield = st.sidebar.slider("最低殖利率 (%)", 0.0, 10.0, 3.0)
cr_roe = st.sidebar.slider("最低 ROE (%)", 0.0, 30.0, 5.0)

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 3. 執行控制")
total_stocks = len(df_stocks)
batch_size = st.sidebar.slider(f"掃描範圍 (建議一次 50 檔)", 0, total_stocks, (0, 50))
start_idx, end_idx = batch_size

# --- 4. 分析邏輯 (增強版) ---
def analyze_stock(ticker_info, criteria):
    try:
        stock = yf.Ticker(ticker_info['yf_ticker'])
        info = stock.info
        
        # 1. 寬鬆的價格檢查
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        if not price:
            return None # 真的抓不到價格才跳過

        # 2. 數據獲取 (缺值補 0 或 999)
        pe = info.get('trailingPE')
        if pe is None: pe = info.get('forwardPE', 999) # 嘗試用預估本益比替補
        
        pb = info.get('priceToBook', 999)
        dy = info.get('dividendYield', 0)
        roe = info.get('returnOnEquity', 0)
        
        if pe is None: pe = 999
        if pb is None: pb = 999
        if dy is None: dy = 0
        if roe is None: roe = 0
        
        dy_pct = dy * 100
        roe_pct = roe * 100
        
        # 3. 條件篩選
        if (pe < criteria['pe'] and pb < criteria['pb'] and 
            dy_pct >= criteria['yield'] and roe_pct >= criteria['roe']):
            
            return {
                '代號': ticker_info['code'],
                '名稱': ticker_info['name'],
                '股價': price,
                '本益比': round(pe, 2) if pe != 999 else "N/A",
                '股價淨值比': round(pb, 2),
                '殖利率(%)': round(dy_pct, 2),
                'ROE(%)': round(roe_pct, 2),
                '產業': info.get('industry', 'N/A')
            }
    except Exception:
        return None
    return None

# --- 5. 執行按鈕 ---
if st.button('開始掃描選股'):
    target_list = df_stocks.iloc[start_idx:end_idx]
    st.write(f"🔍 正在掃描: {start_idx} ~ {end_idx} (共 {len(target_list)} 檔)...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 用於統計失敗原因
    fail_count = 0
    
    for i, (_, row) in enumerate(target_list.iterrows()):
        progress = (i + 1) / len(target_list)
        progress_bar.progress(progress)
        status_text.text(f"分析中: {row['code']} {row['name']}")
        
        criteria = {'pe': cr_pe, 'pb': cr_pb, 'yield': cr_yield, 'roe': cr_roe}
        res = analyze_stock(row, criteria)
        
        if res:
            results.append(res)
        else:
            fail_count += 1
            
        # 重要：強制休息，避免被 Yahoo 封鎖
        time.sleep(0.5)

    progress_bar.empty()
    status_text.text("掃描完成！")
    
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"✅ 找到 {len(df_res)} 檔潛力股！")
        st.dataframe(df_res.style.highlight_max(axis=0, color='lightgreen'), use_container_width=True)
        
        csv = df_res.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載 Excel", csv, "value_stocks.csv", "text/csv")
    else:
        st.error(f"⚠️ 在此區間未發現符合條件的股票。")
        st.warning(f"診斷資訊：已掃描 {len(target_list)} 檔，全部不符合條件或數據抓取失敗。")
        st.info("建議：1. 使用側邊欄「測試 Yahoo 連線」確認 IP 是否被鎖。 2. 嘗試縮小掃描範圍。")
