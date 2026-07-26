import io
import datetime
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import yfinance as yf
import pandas_datareader.data as web
from fredapi import Fred

# 頁面基礎設定：預設收起側邊欄
st.set_page_config(
    layout="wide", 
    page_title="總體經濟監控系統",
    initial_sidebar_state="collapsed"
)

# 隱藏右上角 Streamlit 原生選單與工具列（保留標籤頁與頁面內容）
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

# 側邊欄設定
st.sidebar.markdown("### 系統設定")
api_key = st.secrets.get("FRED_API_KEY", "")
finmind_token = st.secrets.get("FINMIND_TOKEN", "")

# 設定抓取時間範圍（近五年）
end_date = datetime.datetime.now()
start_date = end_date - pd.DateOffset(years=5)

# ================= 資料抓取模組 (美國) =================

@st.cache_data(ttl=3600)
def get_fred_data(series_id, danger_threshold, is_greater_danger=True, key=None):
    try:
        if key:
            fred = Fred(api_key=key)
            data = fred.get_series(series_id, observation_start=start_date, observation_end=end_date)
            df = pd.DataFrame(data, columns=['Value']).dropna().reset_index()
            df.columns = ['Date', 'Value']
        else:
            df = web.DataReader(series_id, 'fred', start_date, end_date).dropna()
            df = df.reset_index()
            df.columns = ['Date', 'Value']

        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

# 製造業新訂單總額 (計算 YoY 年增率，跌破 0% 反紅底)
@st.cache_data(ttl=3600)
def get_amtmno_yoy_data(danger_threshold=0.0, key=None):
    try:
        if key:
            fred = Fred(api_key=key)
            data = fred.get_series("AMTMNO", observation_start=start_date - pd.DateOffset(years=1), observation_end=end_date)
            df = pd.DataFrame(data, columns=['Raw']).dropna().reset_index()
            df.columns = ['Date', 'Raw']
        else:
            df = web.DataReader("AMTMNO", 'fred', start_date - pd.DateOffset(years=1), end_date).dropna().reset_index()
            df.columns = ['Date', 'Raw']

        df['Value'] = df['Raw'].pct_change(12) * 100
        df = df.dropna().reset_index(drop=True)
        df = df[df['Date'] >= start_date].reset_index(drop=True)

        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val < danger_threshold
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

# 聯準會總資產 (計算 4 週變動率 %，突破 3% 反紅底)
@st.cache_data(ttl=3600)
def get_walcl_change_data(danger_threshold=3.0, key=None):
    try:
        if key:
            fred = Fred(api_key=key)
            data = fred.get_series("WALCL", observation_start=start_date - pd.DateOffset(months=2), observation_end=end_date)
            df = pd.DataFrame(data, columns=['Raw']).dropna().reset_index()
            df.columns = ['Date', 'Raw']
        else:
            df = web.DataReader("WALCL", 'fred', start_date - pd.DateOffset(months=2), end_date).dropna().reset_index()
            df.columns = ['Date', 'Raw']

        df['Value'] = df['Raw'].pct_change(4) * 100
        df = df.dropna().reset_index(drop=True)
        df = df[df['Date'] >= start_date].reset_index(drop=True)

        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val > danger_threshold
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

# 商業銀行準備金佔聯準會總資產比例 (%) (TOTRESNS / WALCL * 100，低於 10.0% 反紅底)
@st.cache_data(ttl=3600)
def get_reserve_ratio_data(danger_threshold=10.0, key=None):
    try:
        if key:
            fred = Fred(api_key=key)
            res = fred.get_series("TOTRESNS", observation_start=start_date, observation_end=end_date)
            walcl = fred.get_series("WALCL", observation_start=start_date, observation_end=end_date)
        else:
            res = web.DataReader("TOTRESNS", 'fred', start_date, end_date)['TOTRESNS']
            walcl = web.DataReader("WALCL", 'fred', start_date, end_date)['WALCL']

        df_res = pd.DataFrame(res, columns=['Res']).dropna()
        df_walcl = pd.DataFrame(walcl, columns=['Walcl']).dropna()
        
        df = pd.merge_asof(df_res.sort_index(), df_walcl.sort_index(), left_index=True, right_index=True, direction='nearest')
        df['Value'] = (df['Res'] * 1000 / df['Walcl']) * 100
        df = df.dropna().reset_index()
        df.columns = ['Date', 'Res', 'Walcl', 'Value']

        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val < danger_threshold
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

# 銅金比門檻 (小於 0.0015 反紅底)
@st.cache_data(ttl=3600)
def get_copper_gold_ratio(danger_threshold=0.0015):
    try:
        cu = yf.Ticker("HG=F").history(start=start_date, end=end_date)[['Close']]
        au = yf.Ticker("GC=F").history(start=start_date, end=end_date)[['Close']]
        df = (cu / au).dropna().reset_index()
        df.columns = ['Date', 'Value']
        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val < danger_threshold
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

# ================= 資料抓取模組 (台灣) =================

@st.cache_data(ttl=3600)
def get_taiwan_historical_volatility(danger_threshold=25.0, is_greater_danger=True):
    try:
        df = yf.Ticker("^TWII").history(start=start_date, end=end_date)
        if not df.empty:
            df = df.reset_index()[['Date', 'Close']]
            df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)

            df['Log_Return'] = np.log(df['Close'] / df['Close'].shift(1))
            df['Value'] = df['Log_Return'].rolling(window=20).std() * np.sqrt(252) * 100
            df = df.dropna(subset=['Value'])[['Date', 'Value']].reset_index(drop=True)

            if not df.empty:
                current_val = df['Value'].iloc[-1]
                current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
                is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
                return df, current_val, current_date, is_danger
    except Exception:
        pass
    return pd.DataFrame(), 0, "", False

@st.cache_data(ttl=3600)
def get_taiwan_m1b_m2_data(danger_threshold=0.0):
    url = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/EF15M01.csv"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        import requests.packages.urllib3
        requests.packages.urllib3.disable_warnings()
        
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        res.encoding = 'utf-8'
        df_raw = pd.read_csv(io.StringIO(res.text))

        date_col = df_raw.columns[0]
        m1b_cols = [c for c in df_raw.columns if 'M1B' in str(c) and ('年增率' in str(c) or '%' in str(c))]
        m2_cols = [c for c in df_raw.columns if 'M2' in str(c) and ('年增率' in str(c) or '%' in str(c))]

        m1b_rate_col = m1b_cols[0] if m1b_cols else df_raw.columns[28]
        m2_rate_col = m2_cols[0] if m2_cols else df_raw.columns[30]

        def parse_tw_date(d_str):
            try:
                s = str(d_str).strip()
                if 'M' in s:
                    parts = s.split('M')
                    y, m = int(parts[0]), int(parts[1])
                    if y < 1900:
                        y += 1911
                    return f"{y}-{m:02d}-01"
            except Exception:
                pass
            return None

        df = pd.DataFrame()
        df['Date_str'] = df_raw[date_col].apply(parse_tw_date)
        df['M1B'] = pd.to_numeric(df_raw[m1b_rate_col], errors='coerce')
        df['M2'] = pd.to_numeric(df_raw[m2_rate_col], errors='coerce')

        df = df.dropna(subset=['Date_str', 'M1B', 'M2']).copy()
        df['Date'] = pd.to_datetime(df['Date_str'])
        df['Diff'] = df['M1B'] - df['M2']

        five_years_ago = pd.Timestamp.now() - pd.DateOffset(years=5)
        df = df[df['Date'] >= five_years_ago].sort_values('Date').reset_index(drop=True)

        if df.empty:
            return pd.DataFrame(), 0, "", False

        current_diff = df['Diff'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m')
        is_danger = current_diff < danger_threshold

        return df, current_diff, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

@st.cache_data(ttl=3600)
def get_taiwan_electronics_export_data(danger_threshold=0.0):
    url = "https://web02.mof.gov.tw/njswww/webMain.aspx?sys=220&ym=9000&kind=21&type=4&funid=i8121&cycle=41&outmode=12&compmode=00&outkind=1&fld0=1&codlst0=1101111010100011110111100111110110100&utf=1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.encoding = 'utf-8'
        df = pd.read_csv(io.StringIO(res.text))

        date_col = df.columns[0]
        export_val_col = df.columns[22]

        df = df.dropna(subset=[date_col, export_val_col]).copy()
        df[export_val_col] = pd.to_numeric(df[export_val_col], errors='coerce')
        df['clean_date'] = df[date_col].astype(str).str.strip()
        df = df[df['clean_date'].str.contains('月|\\d{5,}', regex=True)].copy()

        def parse_roc_ym(val):
            val_str = str(val).strip()
            if '年' in val_str and '月' in val_str:
                try:
                    parts = val_str.replace('月', '').split('年')
                    return int(parts[0]), int(parts[1])
                except Exception:
                    return None, None
            elif val_str.isdigit() and len(val_str) == 6:
                try:
                    return int(val_str[:3]), int(val_str[3:])
                except Exception:
                    return None, None
            return None, None

        parsed = df['clean_date'].apply(parse_roc_ym)
        df['roc_year'] = [p[0] for p in parsed]
        df['month'] = [p[1] for p in parsed]

        df = df.dropna(subset=['roc_year', 'month']).copy()
        df['roc_year'] = df['roc_year'].astype(int)
        df['month'] = df['month'].astype(int)

        val_dict = dict(zip(zip(df['roc_year'], df['month']), df[export_val_col]))

        def get_ly_value(row):
            return val_dict.get((row['roc_year'] - 1, row['month']), None)

        df['last_year_val'] = df.apply(get_ly_value, axis=1)
        df['Value'] = ((df[export_val_col] - df['last_year_val']) / df['last_year_val']) * 100

        df['Date'] = pd.to_datetime(df['roc_year'].apply(lambda y: y + 1911).astype(str) + '-' + df['month'].astype(str).str.zfill(2) + '-01')
        df = df.dropna(subset=['Value']).sort_values('Date').reset_index(drop=True)
        
        five_years_ago = pd.Timestamp.now() - pd.DateOffset(years=5)
        df = df[df['Date'] >= five_years_ago].reset_index(drop=True)

        if df.empty:
            return pd.DataFrame(), 0, "", False

        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m')
        is_danger = current_val < danger_threshold

        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

@st.cache_data(ttl=3600)
def get_usdtwd_data(danger_threshold=33.0, is_greater_danger=True):
    try:
        df = yf.Ticker("TWD=X").history(start=start_date, end=end_date)
        df = df.reset_index()[['Date', 'Close']]
        df.columns = ['Date', 'Value']
        current_val = df['Value'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
        return df, current_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, "", False

@st.cache_data(ttl=3600)
def get_taiwan_ma20_bias(overheat_threshold=5.0, breakdown_threshold=-4.0):
    try:
        df_yf = yf.Ticker("^TWII").history(start=start_date, end=end_date).reset_index()
        if not df_yf.empty:
            df_yf['Date'] = pd.to_datetime(df_yf['Date']).dt.tz_localize(None)

            ma20 = df_yf['Close'].rolling(window=20, min_periods=1).mean()
            df_yf['Value'] = ((df_yf['Close'] - ma20) / ma20) * 100.0
            df = df_yf[['Date', 'Value']].dropna().sort_values('Date')

            current_val = df['Value'].iloc[-1]
            current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')

            status = "normal"
            if current_val > overheat_threshold:
                status = "overheat"
            elif current_val < breakdown_threshold:
                status = "breakdown"

            is_danger = (status == "breakdown")  # 僅破位時計入頂部危機總數
            return df, current_val, current_date, status, is_danger
    except Exception:
        pass

    return pd.DataFrame(), 0, "", "normal", False

@st.cache_data(ttl=3600)
def get_tw_futures_chip(token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    url = "https://api.finmindtrade.com/api/v4/data"

    params_tx = {
        "dataset": "TaiwanFuturesInstitutionalInvestors",
        "data_id": "TX",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }

    df_tx = pd.DataFrame()
    tx_val, tx_date, tx_danger = 0, "", False
    try:
        resp_tx = requests.get(url, headers=headers, params=params_tx, timeout=10)
        res_json = resp_tx.json()
        if res_json.get("status") == 200 or "data" in res_json:
            df_tx_raw = pd.DataFrame(res_json.get("data", []))
            if not df_tx_raw.empty:
                df_tx_raw['Date'] = pd.to_datetime(df_tx_raw['date'])
                df_tx_raw['long_open_interest_balance_volume'] = pd.to_numeric(df_tx_raw['long_open_interest_balance_volume'], errors='coerce')
                df_tx_raw['short_open_interest_balance_volume'] = pd.to_numeric(df_tx_raw['short_open_interest_balance_volume'], errors='coerce')

                df_foreign = df_tx_raw[df_tx_raw['institutional_investors'].str.contains('外資', na=False)].copy()
                df_foreign['Value'] = df_foreign['long_open_interest_balance_volume'] - df_foreign['short_open_interest_balance_volume']
                df_tx = df_foreign[['Date', 'Value']].sort_values('Date').groupby('Date').sum().reset_index()

                if not df_tx.empty:
                    tx_val = df_tx['Value'].iloc[-1]
                    tx_date = df_tx['Date'].iloc[-1].strftime('%Y/%m/%d')
                    tx_danger = tx_val < -45000
    except Exception:
        pass

    params_mtx = {
        "dataset": "TaiwanFuturesInstitutionalInvestors",
        "data_id": "MTX",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d")
    }

    df_mtx = pd.DataFrame()
    mtx_val, mtx_date, mtx_danger = 0, "", False
    try:
        resp_mtx = requests.get(url, headers=headers, params=params_mtx, timeout=10)
        res_json_mtx = resp_mtx.json()
        if res_json_mtx.get("status") == 200 or "data" in res_json_mtx:
            df_mtx_raw = pd.DataFrame(res_json_mtx.get("data", []))
            if not df_mtx_raw.empty:
                df_mtx_raw['Date'] = pd.to_datetime(df_mtx_raw['date'])
                df_mtx_raw['long_open_interest_balance_volume'] = pd.to_numeric(df_mtx_raw['long_open_interest_balance_volume'], errors='coerce')
                df_mtx_raw['short_open_interest_balance_volume'] = pd.to_numeric(df_mtx_raw['short_open_interest_balance_volume'], errors='coerce')

                df_mtx_raw['net_oi'] = df_mtx_raw['long_open_interest_balance_volume'] - df_mtx_raw['short_open_interest_balance_volume']
                df_inst = df_mtx_raw.groupby('Date')['net_oi'].sum().reset_index()
                df_inst['Value'] = -df_inst['net_oi']
                df_mtx = df_inst[['Date', 'Value']].sort_values('Date')

                if not df_mtx.empty:
                    mtx_val = df_mtx['Value'].iloc[-1]
                    mtx_date = df_mtx['Date'].iloc[-1].strftime('%Y/%m/%d')
                    mtx_danger = mtx_val > 10000
    except Exception:
        pass

    return df_tx, tx_val, tx_date, tx_danger, df_mtx, mtx_val, mtx_date, mtx_danger

# ================= 視覺化繪圖模組 =================

def draw_line_chart(title, df, is_danger, current_val=0, current_date=""):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            title={'text': title + " (資料加載中)", 'font': {'color': 'gray'}},
            height=250,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
            paper_bgcolor='rgba(0, 0, 0, 0)'
        )
        return fig

    bg_color = 'rgba(255, 235, 235, 1)' if is_danger else 'rgba(255, 255, 255, 1)'
    line_color = 'red' if is_danger else '#1f77b4'

    if "銅金比" in title:
        title_text = f"{title} [{current_date}: {current_val:,.4f}]"
    elif "維持率" in title or "指標" in title or "年增率" in title or "波動率" in title or "變動率" in title:
        title_text = f"{title} [{current_date}: {current_val:,.2f}%]"
    elif "貼現窗口借款" in title:
        title_text = f"{title} [{current_date}: {current_val:,.0f} 百萬美元]"
    elif "外資台指期貨淨未平倉" in title or "散戶小台淨未平倉" in title or "初領失業救濟金" in title:
        title_text = f"{title} [{current_date}: {current_val:,.0f}]"
    else:
        title_text = f"{title} [{current_date}: {current_val:,.2f}]"

    fig = go.Figure()

    if "銅金比" in title and 'SMA200' in df.columns:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Value'], name="銅金比", line=dict(color=line_color, width=2)))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA200'], name="200MA", line=dict(color='gray', width=1.5, dash='dash')))
    else:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Value'], line=dict(color=line_color, width=2)))

    has_legend = "銅金比" in title
    b_margin = 60 if has_legend else 30
    chart_height = 280 if has_legend else 250

    fig.update_layout(
        title={'text': title_text, 'font': {'size': 16, 'color': '#333333'}},
        margin=dict(l=30, r=30, t=40, b=b_margin),
        height=chart_height,
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        uirevision='dataset',
        showlegend=has_legend,
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.25,
            xanchor="center",
            x=0.5
        ),
        xaxis=dict(showgrid=False, type='date', autorange=True, tickfont=dict(color='#333333'), fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor='#e0e0e0', autorange=True, fixedrange=True, tickfont=dict(color='#333333'))
    )
    return fig

def draw_bias_chart(title, df, status, current_val=0, current_date=""):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            title={'text': title + " (資料加載中)", 'font': {'color': 'gray'}},
            height=250,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
            paper_bgcolor='rgba(0, 0, 0, 0)'
        )
        return fig

    if status == "breakdown":
        bg_color = 'rgba(255, 235, 235, 1)'   # 淡紅底 (破位)
        line_color = 'red'
    elif status == "overheat":
        bg_color = 'rgba(255, 235, 200, 1)'   # 淡橘底 (過熱)
        line_color = '#e67e22'
    else:
        bg_color = 'rgba(255, 255, 255, 1)'   # 白底 (正常)
        line_color = '#1f77b4'

    title_text = f"{title} [{current_date}: {current_val:,.2f}%]"

    fig = go.Figure(data=go.Scatter(x=df['Date'], y=df['Value'], line=dict(color=line_color, width=2)))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.7)
    fig.add_hline(y=5.0, line_dash="dot", line_color="#e67e22", opacity=0.6)
    fig.add_hline(y=-4.0, line_dash="dot", line_color="red", opacity=0.6)

    fig.update_layout(
        title={'text': title_text, 'font': {'size': 16, 'color': '#333333'}},
        margin=dict(l=30, r=30, t=40, b=30),
        height=250,
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        uirevision='bias_dataset',
        xaxis=dict(showgrid=False, type='date', autorange=True, tickfont=dict(color='#333333'), fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor='#e0e0e0', autorange=True, fixedrange=True, tickfont=dict(color='#333333'))
    )
    return fig

def draw_m1b_m2_chart(df, is_danger, current_diff, current_date):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            title={'text': "台灣-M1B vs. M2 (資料載入中)", 'font': {'color': 'gray'}},
            height=340,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
            paper_bgcolor='rgba(0, 0, 0, 0)'
        )
        return fig

    bg_color = 'rgba(255, 235, 235, 1)' if is_danger else 'rgba(255, 255, 255, 1)'

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=df['Date'],
            y=df['Diff'],
            name="台灣-M1B-M2(R)",
            marker_color="#f39c12",
            opacity=0.7
        ),
        secondary_y=True
    )

    fig.add_trace(
        go.Scatter(
            x=df['Date'],
            y=df['M2'],
            name="台灣-貨幣總計數M2(年增率,L)",
            line=dict(color="#3498db", width=2)
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=df['Date'],
            y=df['M1B'],
            name="台灣-貨幣總計數M1B(年增率,L)",
            line=dict(color="#e74c3c", width=2)
        ),
        secondary_y=False
    )

    fig.update_layout(
        title={'text': f"台灣-M1B vs. M2 [剪刀差 {current_date}: {current_diff:,.2f}%]", 'font': {'size': 16, 'color': '#333333'}},
        height=340,
        margin=dict(l=30, r=30, t=40, b=60),
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        legend=dict(orientation="h", yanchor="bottom", y=-0.45, xanchor="center", x=0.5, font=dict(color='#333333')),
        bargap=0.4,
        uirevision='m1b_m2_dataset'
    )

    fig.update_yaxes(title_text="Percent (%)", title_font=dict(color='#333333'), tickfont=dict(color='#333333'), secondary_y=False, showgrid=True, gridcolor='#e0e0e0', autorange=True, fixedrange=True)
    fig.update_yaxes(title_text="Percent (%)", title_font=dict(color='#333333'), tickfont=dict(color='#333333'), secondary_y=True, showgrid=False, autorange=True, fixedrange=True)
    fig.update_xaxes(autorange=True, type='date', tickfont=dict(color='#333333'), fixedrange=True)

    return fig

def get_stage_info(danger_count):
    if 0 <= danger_count <= 4:
        return "#1e824c", "正常"
    elif 5 <= danger_count <= 8:
        return "#2ecc71", "注意"
    elif 9 <= danger_count <= 14:
        return "#f1c40f", "警戒"
    elif 15 <= danger_count <= 18:
        return "#e67e22", "危險"
    else:
        return "#e74c3c", "恐慌"

def draw_bar_gauge(danger_count, total_count=22):
    fig = go.Figure()

    sections = [
        {"range": [0, 4], "color": "#1e824c", "label": "正常"},
        {"range": [4, 8], "color": "#2ecc71", "label": "注意"},
        {"range": [8, 14], "color": "#f1c40f", "label": "警戒"},
        {"range": [14, 18], "color": "#e67e22", "label": "危險"},
        {"range": [18, 22], "color": "#e74c3c", "label": "恐慌"}
    ]

    for sec in sections:
        width = sec["range"][1] - sec["range"][0]
        fig.add_trace(go.Bar(
            x=[width],
            y=["狀態"],
            base=[sec["range"][0]],
            orientation='h',
            marker=dict(color=sec["color"]),
            text=f"<b>{sec['label']}</b>",
            textposition='inside',
            insidetextanchor='middle',
            textfont=dict(size=18, color="white"),
            hoverinfo='none',
            showlegend=False
        ))

    fig.add_annotation(
        x=danger_count,
        y="狀態",
        text="▼",
        showarrow=False,
        yshift=48,
        font=dict(size=36, color="#2c3e50")
    )

    fig.update_layout(
        barmode='stack',
        xaxis=dict(range=[0, total_count], showgrid=False, zeroline=False, visible=False, fixedrange=True),
        yaxis=dict(showgrid=False, visible=False, fixedrange=True),
        height=180,
        margin=dict(l=15, r=15, t=40, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

# ================= 介面排版與資料渲染 =================

tab_home, tab_analysis = st.tabs(["首頁", "產業鏈分析"])

with tab_home:

    # 抓取 短期指標 (美國)
    stlfsi_data = get_fred_data("STLFSI4", 2.0, True, api_key)
    vix_data = get_fred_data("VIXCLS", 30.0, True, api_key)
    hy_oas_data = get_fred_data("BAMLH0A0HYM2", 6.0, True, api_key)
    baa_data = get_fred_data("BAA10Y", 3.0, True, api_key)
    dcpf3m_data = get_fred_data("DCPF3M", 5.5, True, api_key)
    dpcredit_data = get_fred_data("DPCREDIT", 10000, True, api_key)
    walcl_data = get_walcl_change_data(3.0, api_key)
    totresns_data = get_reserve_ratio_data(10.0, api_key) 
    icsa_data = get_fred_data("ICSA", 260000, True, api_key)

    # 抓取 中長期指標 (美國)
    t10y2y_data = get_fred_data("T10Y2Y", 0.0, False, api_key)
    t10y3m_data = get_fred_data("T10Y3M", 0.0, False, api_key)
    nosrdisa_data = get_amtmno_yoy_data(0.0, api_key)
    sahm_data = get_fred_data("SAHMREALTIME", 0.5, True, api_key)
    cfnai_data = get_fred_data("CFNAI", -0.7, False, api_key)
    cg_ratio_data = get_copper_gold_ratio(0.0015)

    # 抓取 台灣指標
    twd_data = get_usdtwd_data(33.0, True)
    tw_hv_data = get_taiwan_historical_volatility(25.0, True)
    tw_export_data = get_taiwan_electronics_export_data(0.0)
    tw_m1b_m2_df, tw_m1b_m2_diff, tw_m1b_m2_date, tw_m1b_m2_danger = get_taiwan_m1b_m2_data(0.0)

    # 抓取 大盤月線乖離率 (%)
    tw_bias_df, tw_bias_val, tw_bias_date, tw_bias_status, tw_bias_danger = get_taiwan_ma20_bias(5.0, -5.0)

    # 呼叫 FinMind 期貨籌碼接口
    tw_future_oi_df, tw_future_oi_val, tw_future_oi_date, tw_future_oi_danger, \
    tw_retail_oi_df, tw_retail_oi_val, tw_retail_oi_date, tw_retail_oi_danger = get_tw_futures_chip(finmind_token)

    tw_future_oi_data = (tw_future_oi_df, tw_future_oi_val, tw_future_oi_date, tw_future_oi_danger)
    tw_retail_oi_data = (tw_retail_oi_df, tw_retail_oi_val, tw_retail_oi_date, tw_retail_oi_danger)

    # 統計全部觸發危險的指標數量 (共 22 項)
    danger_total = sum([
        stlfsi_data[3], vix_data[3], hy_oas_data[3], baa_data[3], dcpf3m_data[3],
        dpcredit_data[3], walcl_data[3], totresns_data[3], icsa_data[3],
        t10y2y_data[3], t10y3m_data[3], nosrdisa_data[3], sahm_data[3], cfnai_data[3], cg_ratio_data[3],
        twd_data[3], tw_export_data[3], tw_m1b_m2_danger, tw_bias_danger,
        tw_hv_data[3], tw_future_oi_data[3], tw_retail_oi_data[3]
    ])

    _, stage_text = get_stage_info(danger_total)

    st.plotly_chart(
        draw_bar_gauge(danger_total, 22), 
        use_container_width=True, 
        config={'staticPlot': True}
    )
    
    st.markdown(f"<h4 style='text-align: center; color: gray;'>數據監控儀表板：{stage_text} ({danger_total} / 22 項)</h4>", unsafe_allow_html=True)
    st.divider()

    st.markdown("### 美國經濟指標")
    st.subheader("短期指標 (流動性與壓力)")

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(draw_line_chart("金融壓力指數 (STLFSI4)", stlfsi_data[0], stlfsi_data[3], stlfsi_data[1], stlfsi_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控金融體系流動性與壓力。<br>**判斷方式：** 數值 0 代表歷史平均。大於 0 代表壓力升高。<br>**危機標準：** 數值快速攀升並突破 2.0。", unsafe_allow_html=True)
    with col2:
        st.plotly_chart(draw_line_chart("VIX 恐慌指數 (VIXCLS)", vix_data[0], vix_data[3], vix_data[1], vix_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控市場恐慌情緒與波動預期。<br>**判斷方式：** 數值急升代表市場避險情緒飆高。<br>**危機標準：** 數值突破 30 為實質恐慌。", unsafe_allow_html=True)

    st.write("---")

    col3, col4 = st.columns(2)
    with col3:
        st.plotly_chart(draw_line_chart("高收益債利差 (BAMLH0A0HYM2)", hy_oas_data[0], hy_oas_data[3], hy_oas_data[1], hy_oas_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 衡量市場風險偏好與高風險企業違約機率。<br>**判斷方式：** 利差飆升代表機構大舉拋售高風險資產。<br>**危機標準：** 利差突破 6.0% 代表避險情緒升溫。", unsafe_allow_html=True)
    with col4:
        st.plotly_chart(draw_line_chart("Baa 級企業債利差 (BAA10Y)", baa_data[0], baa_data[3], baa_data[1], baa_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控中等信用評級企業的融資成本與壓力。<br>**判斷方式：** 利差擴大代表實體企業籌資困難。<br>**危機標準：** 利差快速飆升並突破 3.0%。", unsafe_allow_html=True)

    st.write("---")

    col5, col6 = st.columns(2)
    with col5:
        st.plotly_chart(draw_line_chart("金融商業本票利率 (DCPF3M)", dcpf3m_data[0], dcpf3m_data[3], dcpf3m_data[1], dcpf3m_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控企業短期無擔保融資成本。<br>**判斷方式：** 利率高檔攀升代表企業借貸成本增加。<br>**危機標準：** 利率絕對值突破 5.5% 反映融資壓力高漲。", unsafe_allow_html=True)
    with col6:
        st.plotly_chart(draw_line_chart("貼現窗口借款 (DPCREDIT)", dpcredit_data[0], dpcredit_data[3], dpcredit_data[1], dpcredit_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控銀行體系應對緊急流動性缺口之需求。<br>**判斷方式：** 正常情況下借款金額趨近於零。<br>**危機標準：** 借款規模突破 25,000 百萬美元，反映金融機構出現極端流動性危機。", unsafe_allow_html=True)

    st.write("---")

    col7, col8 = st.columns(2)
    with col7:
        st.plotly_chart(draw_line_chart("聯準會總資產近月變動率 (WALCL)", walcl_data[0], walcl_data[3], walcl_data[1], walcl_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監測聯準會是否進行緊急擴表注水。<br>**判斷方式：** 資產規模短期內急遽膨脹代表市場發生系統性風險。<br>**危機標準：** 近 4 週資產規模變動率突破 +3.0%。", unsafe_allow_html=True)
    with col8:
        st.plotly_chart(draw_line_chart("商業銀行準備金年增率 (TOTRESNS)", totresns_data[0], totresns_data[3], totresns_data[1], totresns_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監測美國銀行體系的基礎流動性池變化。<br>**判斷方式：** 準備金年增率大幅下滑代表金融體系資金遭持續抽離。<br>**危機標準：** 年增率跌破 -5.0%，反映銀行體系流動性水位降至警戒區。", unsafe_allow_html=True)

    st.write("---")

    col9, col10 = st.columns(2)
    with col9:
        st.plotly_chart(draw_line_chart("初領失業救濟金 (ICSA)", icsa_data[0], icsa_data[3], icsa_data[1], icsa_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控勞動力市場短期動能與裁員狀況。<br>**判斷方式：** 趨勢持續向上代表企業加速裁員。<br>**危機標準：** 數值連續數週突破 26 萬人，反映就業市場明顯惡化。", unsafe_allow_html=True)
    with col10:
        st.write("")

    st.divider()
    st.subheader("中長期指標 (經濟活動與衰退預警)")

    col11, col12 = st.columns(2)
    with col11:
        st.plotly_chart(draw_line_chart("10年減2年期利差 (T10Y2Y)", t10y2y_data[0], t10y2y_data[3], t10y2y_data[1], t10y2y_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 評估中長期經濟衰退風險與殖利率曲線型態。<br>**判斷方式：** 觀察利差是否跌破 0（倒掛）與倒掛後是否急速回升。<br>**危機標準：** 1.預警期：利差跌破 0 進入倒掛。<br>2.爆發期：深度倒掛後急速反彈突破 0 轉正（陡峭化）。", unsafe_allow_html=True)
    with col12:
        st.plotly_chart(draw_line_chart("10年減3個月期利差 (T10Y3M)", t10y3m_data[0], t10y3m_data[3], t10y3m_data[1], t10y3m_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 聯準會最看重的衰退預警指標。<br>**判斷方式：** 觀察短期資金成本與長端景氣預期的落差及轉折。<br>**危機標準：** 1.預警期：利差跌破 0 進入倒掛。<br>2.爆發期：結束倒掛並急促拉升轉正（降息循環與衰退降臨）。", unsafe_allow_html=True)

    st.write("---")

    col13, col14 = st.columns(2)
    with col13:
        st.plotly_chart(draw_line_chart("製造業新訂單總額年增率 (AMTMNO)", nosrdisa_data[0], nosrdisa_data[3], nosrdisa_data[1], nosrdisa_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 預判製造業擴張或收縮之領先指標。<br>**判斷方式：** 觀察新訂單總額之年對年成長動能。<br>**危機標準：** 年增率 (YoY) 跌破 0.0% 反映製造業進入收縮期。", unsafe_allow_html=True)
    with col14:
        st.plotly_chart(draw_line_chart("薩姆規則 (SAHMREALTIME)", sahm_data[0], sahm_data[3], sahm_data[1], sahm_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 即時判定經濟是否已步入衰退。<br>**判斷方式：** 計算失業率移動平均值與低點差值。<br>**危機標準：** 差值突破 0.5 個百分點。", unsafe_allow_html=True)

    st.write("---")

    col15, col16 = st.columns(2)
    with col15:
        st.plotly_chart(draw_line_chart("芝加哥全國活動指數 (CFNAI)", cfnai_data[0], cfnai_data[3], cfnai_data[1], cfnai_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 綜合評估整體經濟活動成長率。<br>**判斷方式：** 小於 0 為低於歷史趨勢。<br>**危機標準：** 三個月移動平均值跌破 -0.7。", unsafe_allow_html=True)
    with col16:
        st.plotly_chart(draw_line_chart("銅金比", cg_ratio_data[0], cg_ratio_data[3], cg_ratio_data[1], cg_ratio_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 衡量市場風險偏好與景氣擴張力道。<br>**判斷方式：** 數值持續低迷代表市場避險情緒濃厚且實體需求孱弱。<br>**危機標準：** 銅金比絕對值跌破 0.0015 水準。", unsafe_allow_html=True)

    st.divider()
    st.subheader("台灣經濟及股市指標")

    st.markdown("#### 基本面")
    tw_basic1, tw_basic2 = st.columns(2)
    with tw_basic1:
        st.plotly_chart(draw_line_chart("財政部電子零組件出口年增率", tw_export_data[0], tw_export_data[3], tw_export_data[1], tw_export_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 預判台股半導體與科技業基本面轉折。<br>**判斷方式：** 趨勢領先台股科技企業營收約 1 至 2 個月。<br>**危機標準：** 年增率高檔反轉且由正轉負。", unsafe_allow_html=True)
    with tw_basic2:
        st.write("")

    st.write("---")

    st.markdown("#### 資金面")
    tw_fund1, tw_fund2 = st.columns(2)
    with tw_fund1:
        st.plotly_chart(draw_line_chart("美元兌新台幣匯率 (USD/TWD)", twd_data[0], twd_data[3], twd_data[1], twd_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控外資資金進出台股動向與匯率風險。<br>**判斷方式：** 台幣貶值通常伴隨外資賣超台股。<br>**危機標準：** 台幣短時間內急速貶值並突破關鍵整數防線（33.0）。", unsafe_allow_html=True)
    with tw_fund2:
        st.plotly_chart(draw_m1b_m2_chart(tw_m1b_m2_df, tw_m1b_m2_danger, tw_m1b_m2_diff, tw_m1b_m2_date), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 衡量國內股市資金動態與流動性。<br>**判斷方式：** M1B 年增率大於 M2 屬資金動能充沛。<br>**危機標準：** M1B 年增率急遽下滑並由上往下穿透 M2（死亡交叉）。", unsafe_allow_html=True)

    st.write("---")

    st.markdown("#### 籌碼面")
    
    tw_chip1, tw_chip2 = st.columns(2)
    with tw_chip1:
        st.plotly_chart(draw_line_chart("台指期歷史波動率 (20日HV)", tw_hv_data[0], tw_hv_data[3], tw_hv_data[1], tw_hv_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 監控台股大盤短線價格真實劇烈變動程度。<br>**判斷方式：** 數值急升代表台股大盤短線走勢轉趨劇烈。<br>**危機標準：** 年化歷史波動率突破 25.0% 進入高風險狀態。", unsafe_allow_html=True)
    with tw_chip2:
        st.plotly_chart(draw_bias_chart("大盤乖離冷熱指標", tw_bias_df, tw_bias_status, tw_bias_val, tw_bias_date), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 觀察台股大盤相對於月線（20MA）的價格偏離程度，判定短線過熱或乖離過大。<br>**判斷方式：** 0% 為基準線。高於 +5% 短線過熱；低於 -4% 短線超賣乖離過大。<br>**危機標準：** 跌破 -4.0% 反映短線價格結構轉弱與修正壓力。", unsafe_allow_html=True)

    st.write("---")

    tw_chip3, tw_chip4 = st.columns(2)
    with tw_chip3:
        st.plotly_chart(draw_line_chart("外資台指期貨淨未平倉", tw_future_oi_data[0], tw_future_oi_data[3], tw_future_oi_data[1], tw_future_oi_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 觀察外資對台股大盤的避險情緒。<br>**判斷方式：** 排除常態避險後，淨空單增加代表避險看壞，重點在於短線空單激增速度。<br>**危機標準：** 淨空單大量累積突破 45,000 口且現貨同步賣超。", unsafe_allow_html=True)
    with tw_chip4:
        st.plotly_chart(draw_line_chart("散戶小台淨未平倉", tw_retail_oi_data[0], tw_retail_oi_data[3], tw_retail_oi_data[1], tw_retail_oi_data[2]), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 觀察散戶期貨部位，作為極端行情的反指標。<br>**判斷方式：** 散戶於大盤下跌時大幅加碼淨多單追跌抄底，代表籌碼沉澱不良，易引發多頭踩踏。<br>**危機標準：** 散戶淨多單異常激增（突破 10,000 口）且大盤持續破底。", unsafe_allow_html=True)

with tab_analysis:
    st.write("產業鏈分析模組建置中...")
