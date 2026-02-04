import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import time

# --- 1. 頁面設定 ---
st.set_page_config(page_title="台股價值大師雷達", layout="wide")

st.title("📊 台股價值投資掃描器")
st.markdown("""
**策略邏輯：** 尋找低本益比、低股價淨值比、高殖利率且具備護城河(ROE)的優質公司。
> *「別人恐懼時我貪婪，但前提是你知道東西的價值。」*
""")

# --- 2. 側邊欄：參數設定 ---
st.sidebar.header("⚙️ 篩選大師設定")

# 獲取全台股票清單的函數
@st.cache_data(ttl=86400) # 緩存 24 小時，避免重複抓取
def get_tw_stock_list():
    """
    從證交所與櫃買中心抓取所有股票代號
    """
    try:
        # 上市股票 (Mode=2)
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        res_twse = requests.get(url_twse)
        df_twse = pd.read_html(res_twse.text)[0]
        
        # 上櫃股票 (Mode=4)
        url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        res_tpex = requests.get(url_tpex)
        df_tpex = pd.read_html(res_tpex.text)[0]
        
        # 整理數據
        def clean_data(df, suffix):
            df = df.iloc[2:] # 去掉標頭
            df.columns = df.iloc[0] # 設定欄位
            df = df.dropna(thresh=3, axis=0) # 刪除空行
            df = df[df['有價證券代號及名稱'].astype(str).str.contains('　')] # 篩選有代號的
            
            # 拆分代號與名稱
            df['code'] = df['有價證券代號及名稱'].str.split('　').str[0]
            df['name'] = df['有價證券代號及名稱'].str.split('　').str[1]
            
            # 只要股票 (過濾掉權證等，股票代號通常為4碼)
            df = df[df['code'].str.len() == 4]
            
            # 加入 yfinance 格式後綴
            df['yf_ticker'] = df['code'] + suffix
            return df[['code', 'name', 'yf_ticker']]

        df_listed = clean_data(df_twse, ".TW")
        df_otc = clean_data(df_tpex, ".TWO")
        
        # 合併
        df_all = pd.concat([df_listed, df_otc], ignore_index=True)
        return df_all
        
    except Exception as e:
        st.error(f"抓取股票清單失敗: {e}")
        return pd.DataFrame()

# 載入股票清單
with st.spinner('正在更新全台股清單...'):
    df_stocks = get_tw_stock_list()

if not df_stocks.empty:
    st.sidebar.success(f"已載入 {len(df_stocks)} 檔上市櫃股票")
else:
    st.sidebar.error("無法載入股票清單")

# 篩選參數 UI
cr_pe = st.sidebar.number_input("最大本益比 (P/E)", value=15.0)
cr_pb = st.sidebar.number_input("最大股價淨值比 (P/B)", value=1.5)
cr_yield = st.sidebar.slider("最低殖利率 (%)", 0.0, 10.0, 4.0)
cr_roe = st.sidebar.slider("最低 ROE (%)", 0.0, 30.0, 10.0)

# 批次處理設定 (解決 Streamlit 超時問題)
st.sidebar.markdown("---")
st.sidebar.subheader("🚀 執行控制")
batch_size = st.sidebar.slider("掃描範圍 (避免超時，建議分批)", 0, len(df_stocks), (0, 100))
start_idx, end_idx = batch_size

# --- 3. 核心分析邏輯 ---
def analyze_stock(ticker_info, criteria):
    ticker = ticker_info['yf_ticker']
    name = ticker_info['name']
    
    try:
        stock = yf.Ticker(ticker)
        # 為了加速，只抓 info，若失敗則跳過
        info = stock.info
        
        if 'currentPrice' not in info:
            return None

        # 獲取指標
        pe = info.get('trailingPE', 999) # 若無數據設為高值
        pb = info.get('priceToBook', 999)
        dy = info.get('dividendYield', 0)
        roe = info.get('returnOnEquity', 0)
        
        # 處理 None 的情況
        if dy is None: dy = 0
        if roe is None: roe = 0
        
        # 轉換為百分比
        dy_pct = dy * 100
        roe_pct = roe * 100
        
        # 篩選判斷
        if (pe < criteria['pe'] and 
            pb < criteria['pb'] and 
            dy_pct > criteria['yield'] and 
            roe_pct > criteria['roe']):
            
            return {
                '代號': ticker_info['code'],
                '名稱': name,
                '股價': info.get('currentPrice'),
                '本益比': round(pe, 2),
                '股價淨值比': round(pb, 2),
                '殖利率(%)': round(dy_pct, 2),
                'ROE(%)': round(roe_pct, 2),
                '產業': info.get('industry', 'N/A')
            }
            
    except Exception:
        return None
    return None

# --- 4. 主執行按鈕 ---
if st.button('開始掃描選股'):
    target_stocks = df_stocks.iloc[start_idx:end_idx]
    st.write(f"正在掃描第 {start_idx} 到 {end_idx} 檔，共 {len(target_stocks)} 檔股票...")
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # 迴圈執行
    for i, (_, row) in enumerate(target_stocks.iterrows()):
        # 更新進度
        progress = (i + 1) / len(target_stocks)
        progress_bar.progress(progress)
        status_text.text(f"分析中: {row['code']} {row['name']} ...")
        
        # 執行分析
        criteria = {'pe': cr_pe, 'pb': cr_pb, 'yield': cr_yield, 'roe': cr_roe}
        res = analyze_stock(row, criteria)
        
        if res:
            results.append(res)
        
        # 輕微延遲避免被鎖 IP (雖然您不在乎時間，但為了成功率)
        time.sleep(0.1)

    progress_bar.empty()
    status_text.empty()

    # --- 5. 展示結果 ---
    if results:
        df_res = pd.DataFrame(results)
        st.success(f"✅ 掃描完成！共發現 {len(df_res)} 檔潛力股")
        
        # 互動式表格
        st.dataframe(df_res.style.highlight_max(axis=0, color='lightgreen'), use_container_width=True)
        
        # 下載按鈕
        csv = df_res.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載 Excel (CSV)",
            data=csv,
            file_name='value_stocks.csv',
            mime='text/csv',
        )
        
        # 大師總結
        st.markdown("---")
        st.markdown(f"""
        ### 👨‍🏫 股票大師觀點
        這次掃描從 **{len(target_stocks)}** 檔中篩選出了 **{len(df_res)}** 檔標的。
        
        **建議下一步：**
        1. 觀察這些公司的 **「自由現金流」** 是否為正。
        2. 檢查其所屬產業目前是否處於 **「景氣循環低點」**。
        3. 分散佈局，不要單壓一檔。
        """)
        
    else:
        st.warning("⚠️ 在此區間內未發現符合條件的股票，請嘗試放寬條件或掃描其他區間。")
