import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import urllib3
from io import StringIO

# --- 0. 基礎設定 ---
st.set_page_config(page_title="台股價值大師雷達", layout="wide")
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 介面標題 ---
st.title("📊 台股價值投資掃描器")
st.markdown("""
**策略邏輯：** 尋找低本益比、低股價淨值比、高殖利率且具備護城河(ROE)的優質公司。
> *「別人恐懼時我貪婪，但前提是你知道東西的價值。」*
""")

# --- 2. 核心功能：獲取股票清單 (含救生圈模式) ---
@st.cache_data(ttl=86400)
def get_tw_stock_list():
    """
    嘗試從證交所抓取。若失敗，則回傳內建的台灣50名單，確保程式可用。
    """
    status_placeholder = st.empty()
    status_placeholder.text("正在連線證交所抓取最新清單...")

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        
        # 定義通用處理函數
        def fetch_and_process(url, suffix):
            response = requests.get(url, verify=False, headers=headers)
            response.encoding = 'big5' # 強制編碼
            
            # 使用 StringIO 避免 pandas 警告
            dfs = pd.read_html(StringIO(response.text))
            if not dfs: return pd.DataFrame()
            
            df = dfs[0]
            
            # 自動尋找標題行
            header_idx = -1
            for i in range(min(5, len(df))):
                row_str = str(df.iloc[i].values)
                if '有價證券代號' in row_str:
                    header_idx = i
                    break
            
            if header_idx == -1: return pd.DataFrame()

            # 重設標題
            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx+1:].copy()
            
            # 清洗數據
            df = df.dropna(subset=['有價證券代號及名稱'])
            # 確保有分隔符號
            df = df[df['有價證券代號及名稱'].astype(str).str.contains('　')]
            
            # 拆分代號
            df['code'] = df['有價證券代號及名稱'].str.split('　').str[0]
            df['name'] = df['有價證券代號及名稱'].str.split('　').str[1]
            
            # 只留股票 (4碼)
            df = df[df['code'].str.len() == 4]
            
            # 建立 yfinance 代號
            df['yf_ticker'] = df['code'] + suffix
            
            return df[['code', 'name', 'yf_ticker']]

        # 抓取上市
        df_tw = fetch_and_process("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", ".TW")
        # 抓取上櫃
        df_two = fetch_and_process("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", ".TWO")
        
        # 合併
        df_final = pd.concat([df_tw, df_two], ignore_index=True)
        
        if df_final.empty:
            raise Exception("抓取到的清單為空")

        status_placeholder.success(f"成功抓取 {len(df_final)} 檔股票！")
        return df_final

    except Exception as e:
        status_placeholder.warning(f"無法連線證交所 ({e})，已切換至「救生圈模式」(載入台灣50成分股)")
        
        # 救生圈名單 (手動內建常用50檔，確保 APP 永遠能跑)
        fallback_data = [
            {"code": "2330", "name": "台積電", "yf_ticker": "2330.TW"},
            {"code": "2317", "name": "鴻海", "yf_ticker": "2317.TW"},
            {"code": "2454", "name": "聯發科", "yf_ticker": "2454.TW"},
            {"code": "2308", "name": "台達電", "yf_ticker": "2308.TW"},
            {"code": "2881", "name": "富邦金", "yf_ticker": "2881.TW"},
            {"code": "2412", "name": "中華電", "yf_ticker": "2412.TW"},
            {"code": "1301", "name": "台塑", "yf_ticker": "1301.TW"},
            {"code": "1303", "name": "南亞", "yf_ticker": "1303.TW"},
            {"code": "2882", "name": "國泰金", "yf_ticker": "2882.TW"},
            {"code": "2002", "name": "中鋼", "yf_ticker": "2002.TW"},
            {"code": "2886", "name": "兆豐金", "yf_ticker": "2886.TW"},
            {"code": "2891", "name": "中信金", "yf_ticker": "2891.TW"},
            {"code": "2884", "name": "玉山金", "yf_ticker": "2884.TW"},
            {"code": "1216", "name": "統一", "yf_ticker": "1216.TW"},
            {"code": "5880", "name": "合庫金", "yf_ticker": "5880.TW"},
            {"code": "2892", "name": "第一金", "yf_ticker": "2892.TW"},
            {"code": "1101", "name": "台泥", "yf_ticker": "1101.TW"},
            {"code": "2382", "name": "廣達", "yf_ticker": "2382.TW"},
            {"code": "2357", "name": "華碩", "yf_ticker": "2357.TW"},
            {"code": "3231", "name": "緯創", "yf_ticker": "3231.TW"},
            # 可以自行擴充...
        ]
        return pd.DataFrame(fallback_data)

# 載入資料
df_stocks = get_tw_stock_list()

# --- 3. 側邊欄設定 ---
st.sidebar.header("⚙️ 篩選參數")
cr_pe = st.sidebar.number_input("最大本益比 (P/E)", value=15.0)
cr_pb = st.sidebar.number_input("最大股價淨值比 (P/B)", value=1.5)
cr_yield = st.sidebar.slider("最低殖利率 (%)", 0.0, 10.0, 4.0)
cr_roe = st.sidebar.slider("最低 ROE (%)", 0.0, 30.0, 10.0)

st.sidebar.markdown("---")
st.sidebar.subheader("🚀 執行控制")

# 動態調整滑桿上限
total_stocks = len(df_stocks)
batch_size = st.sidebar.slider(
    f"掃描範圍 (共 {total_stocks} 檔)", 
    0, 
    total_stocks, 
    (0, min(100, total_stocks)) # 預設只跑前100檔
)
start_idx, end_idx = batch_size

# --- 4. 分析邏輯 ---
def analyze_stock(ticker_info, criteria):
    try:
        stock = yf.Ticker(ticker_info['yf_ticker'])
        info = stock.info
        
        if 'currentPrice' not in info: return None

        # 取得數據 (若無數據則給予不通過的預設值)
        pe = info.get('trailingPE', 999) 
        pb = info.get('priceToBook', 999)
        dy = info.get('dividendYield', 0)
        roe = info.get('returnOnEquity', 0)
        
        # 修正 NoneType
        if pe is None: pe = 999
        if pb is None: pb = 999
        if dy is None: dy = 0
        if roe is None: roe = 0
        
        dy_pct = dy * 100
        roe_pct = roe * 100
        
        # 篩選
        if (pe < criteria['pe'] and pb < criteria['pb'] and 
            dy_pct > criteria['yield'] and roe_pct > criteria['roe']):
            
            return {
                '代號': ticker_info['code'],
                '名稱': ticker_info['name'],
                '股價': info.get('currentPrice'),
                '本益比': round(pe, 2),
                '股價淨值比': round(pb, 2),
                '殖利率(%)': round(dy_pct, 2),
                'ROE(%)': round(roe_pct, 2),
                '產業': info.get('industry', 'N/A')
            }
    except:
        return None
    return None

# --- 5. 執行按鈕 ---
if st.button('開始掃描選股'):
    target_list = df_stocks.iloc[start_idx:end_idx]
    st.write(f"正在掃描: {start_idx} ~ {end_idx} (共 {len(target_list)} 檔)...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, (_, row) in enumerate(target_list.iterrows()):
        progress = (i + 1) / len(target_list)
        progress_bar.progress(progress)
        status_text.text(f"分析中: {row['code']} {row['name']}")
        
        criteria = {'pe': cr_pe, 'pb': cr_pb, 'yield': cr_yield, 'roe': cr_roe}
        res = analyze_stock(row, criteria)
        if res: results.append(res)
        
    progress_bar.empty()
    status_text.text("掃描完成！")
    
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"✅ 找到 {len(df_res)} 檔潛力股！")
        st.dataframe(df_res.style.highlight_max(axis=0, color='lightgreen'), use_container_width=True)
        
        # CSV 下載
        csv = df_res.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 下載 Excel", csv, "value_stocks.csv", "text/csv")
    else:
        st.warning("在此區間未發現符合條件的股票，請放寬條件試試。")
