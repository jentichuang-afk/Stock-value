import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import urllib3

# --- 0. 基礎設定與修復 ---
st.set_page_config(page_title="台股價值大師雷達", layout="wide")

# 1. 忽略 SSL 警告 (解決圖一的 CERTIFICATE_VERIFY_FAILED)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 1. 介面標題 ---
st.title("📊 台股價值投資掃描器")
st.markdown("""
**策略邏輯：** 尋找低本益比、低股價淨值比、高殖利率且具備護城河(ROE)的優質公司。
> *「別人恐懼時我貪婪，但前提是你知道東西的價值。」*
""")

# --- 2. 側邊欄：參數設定 ---
st.sidebar.header("⚙️ 篩選大師設定")

# --- 核心功能：獲取全台股票清單 (修復版) ---
@st.cache_data(ttl=86400) # 緩存 24 小時
def get_tw_stock_list():
    """
    從證交所與櫃買中心抓取所有股票代號 (強健修復版)
    """
    try:
        # 偽裝 header
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

        # 定義抓取函數
        def fetch_and_parse(url):
            # verify=False 解決 SSL 問題
            res = requests.get(url, verify=False, headers=headers)
            # 強制設定編碼，避免亂碼導致找不到欄位
            res.encoding = 'big5' 
            
            # 使用 pandas 讀取 HTML
            dfs = pd.read_html(res.text)
            if not dfs:
                return pd.DataFrame()
            
            df = dfs[0]
            
            # --- 關鍵修正：自動尋找標題行 (解決圖二錯誤) ---
            # 不再假設標題在第幾行，而是掃描前 5 行尋找關鍵字
            header_row_index = -1
            for i in range(min(5, len(df))):
                # 將該行轉為字串檢查是否包含關鍵欄位名
                row_str = str(df.iloc[i].values)
                if '有價證券代號' in row_str and '名稱' in row_str:
                    header_row_index = i
                    break
            
            if header_row_index == -1:
                return pd.DataFrame() # 找不到標題，回傳空表

            # 設定正確的標題
            df.columns = df.iloc[header_row_index]
            # 資料從標題的下一行開始
            df = df.iloc[header_row_index + 1:]
            
            return df

        # 上市股票 (Mode=2)
        url_twse = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        df_listed = fetch_and_parse(url_twse)
        
        # 上櫃股票 (Mode=4)
        url_tpex = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        df_otc = fetch_and_parse(url_tpex)
        
        # 合併並清洗
        df_all = pd.concat([df_listed, df_otc], ignore_index=True)
        
        # 資料清洗
        # 1. 移除沒有代號的行
        df_all = df_all.dropna(subset=['有價證券代號及名稱'])
        # 2. 確保包含分隔符號
        df_all = df_all[df_all['有價證券代號及名稱'].astype(str).str.contains('　')]
        
        # 拆分代號與名稱
        df_all['code'] = df_all['有價證券代號及名稱'].str.split('　').str[0]
        df_all['name'] = df_all['有價證券代號及名稱'].str.split('　').str[1]
        
        # 只要股票 (代號為 4 碼)
        df_all = df_all[df_all['code'].str.len() == 4]
        
        # 加入後綴
        # 簡單判斷：上市加 .TW, 上櫃暫時也加 .TW (yfinance 支援度較好) 或 .TWO
        # 這裡我們用一個簡單邏輯：如果在 df_listed 裡就是 .TW，否則 .TWO
        # 為了簡化，我們先統一加 .TW，若找不到再試 .TWO (或直接依照來源區分)
        
        # 更精準的做法：
        df_listed['yf_ticker'] = df_listed['code'] + '.TW'
        df_otc['yf_ticker'] = df_otc['code'] + '.TWO'
        
        # 重新合併帶有 yf_ticker 的資料
        # 注意：上面的 df_all 是混合的，這裡我們用乾淨的邏輯重組
        final_list = []
        
        # 處理上市
        for _, row in df_listed.iterrows():
            if isinstance(row['有價證券代號及名稱'], str) and '　' in row['有價證券代號及名稱']:
                c, n = row['有價證券代號及名稱'].split('　')[:2]
                if len(c) == 4:
                    final_list.append({'code': c, 'name': n, 'yf_ticker': f"{c}.TW"})
                    
        # 處理上櫃
        for _, row in df_otc.iterrows():
             if isinstance(row['有價證券代號及名稱'], str) and '　' in row['有價證券代號及名稱']:
                c, n = row['有價證券代號及名稱'].split('　')[:2]
                if len(c) == 4:
                    final_list.append({'code': c, 'name': n, 'yf_ticker': f"{c}.TWO"})
        
        return pd.DataFrame(final_list)
        
    except Exception as e:
        st.error(f"抓取股票清單失敗 (詳細錯誤): {e}")
        return pd.DataFrame()

# 載入股票清單
with st.spinner('正在更新全台股清單 (已啟用 SSL 繞過模式)...'):
    df_stocks = get_tw_stock_list()

if not df_stocks.empty:
    st.sidebar.success(f"已載入 {len(df_stocks)} 檔上市櫃股票")
else:
    st.sidebar.error("無法載入股票清單，請檢查連線。")

# 篩選參數 UI
cr_pe = st.sidebar.number_input("最大本益比 (P/E)", value=15.0)
cr_pb = st.sidebar.number_input("最大股價淨值比 (P/B)", value=1.5)
cr_yield = st.sidebar.slider("最低殖利率 (%)", 0.0, 10.0, 4.0)
cr_roe = st.sidebar.slider("最低 ROE (%)", 0.0, 30.0, 10.0)

# 批次處理設定
st.sidebar.markdown("---")
st.sidebar.subheader("🚀 執行控制")
batch_size = st.sidebar.slider("掃描範圍 (建議分批)", 0, len(df_stocks) if not df_stocks.empty else 100, (0, 100))
start_idx, end_idx = batch_size

# --- 3. 單一股票分析邏輯 ---
def analyze_stock(ticker_info, criteria):
    ticker = ticker_info['yf_ticker']
    name = ticker_info['name']
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if 'currentPrice' not in info:
            return None

        pe = info.get('trailingPE', 999) 
        pb = info.get('priceToBook', 999)
        dy = info.get('dividendYield', 0)
        roe = info.get('returnOnEquity', 0)
        
        if dy is None: dy = 0
        if roe is None: roe = 0
        if pe is None: pe = 999
        if pb is None: pb = 999
        
        dy_pct = dy * 100
        roe_pct = roe * 100
        
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
    if df_stocks.empty:
        st.error("股票清單未載入，無法開始。")
    else:
        target_stocks = df_stocks.iloc[start_idx:end_idx]
        st.write(f"正在掃描第 {start_idx} 到 {end_idx} 檔，共 {len(target_stocks)} 檔股票...")
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total = len(target_stocks)
        for i, (_, row) in enumerate(target_stocks.iterrows()):
            progress = (i + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"分析中 ({i+1}/{total}): {row['code']} {row['name']} ...")
            
            criteria = {'pe': cr_pe, 'pb': cr_pb, 'yield': cr_yield, 'roe': cr_roe}
            res = analyze_stock(row, criteria)
            
            if res:
                results.append(res)
            
            # 輕微延遲
            time.sleep(0.1)

        progress_bar.empty()
        status_text.text("掃描完成！")

        if results:
            df_res = pd.DataFrame(results)
            st.success(f"✅ 掃描完成！在此區間共發現 {len(df_res)} 檔潛力股")
            st.dataframe(df_res.style.highlight_max(axis=0, color='lightgreen'), use_container_width=True)
            
            csv = df_res.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載 Excel (CSV)",
                data=csv,
                file_name=f'value_stocks_{start_idx}_{end_idx}.csv',
                mime='text/csv',
            )
        else:
            st.warning("⚠️ 在此區間內未發現符合條件的股票。")
