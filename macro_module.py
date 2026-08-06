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


# ================= 資料抓取模組 (通用與美股) =================

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
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# 殖利率曲線動態轉折檢測
@st.cache_data(ttl=3600)
def get_yield_curve_steepening_data(series_id, key=None):
    try:
        if key:
            fred = Fred(api_key=key)
            data = fred.get_series(series_id, observation_start=start_date - pd.DateOffset(months=7), observation_end=end_date)
            df = pd.DataFrame(data, columns=['Value']).dropna().reset_index()
            df.columns = ['Date', 'Value']
        else:
            df = web.DataReader(series_id, 'fred', start_date - pd.DateOffset(months=7), end_date).dropna().reset_index()
            df.columns = ['Date', 'Value']

        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
        
        current_val = df['Value'].iloc[-1]
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        
        six_months_ago = df['Date'].iloc[-1] - pd.DateOffset(months=6)
        one_month_ago = df['Date'].iloc[-1] - pd.DateOffset(months=1)
        
        df_6m = df[df['Date'] >= six_months_ago]
        had_inversion = (df_6m['Value'] < 0.0).any()
        
        val_1m_ago = df[df['Date'] <= one_month_ago]['Value'].iloc[-1] if not df[df['Date'] <= one_month_ago].empty else current_val
        steepening = (current_val - val_1m_ago) > 0.5
        
        is_danger = had_inversion and steepening and (current_val > 0.0)
        
        df_display = df[df['Date'] >= start_date].reset_index(drop=True)
        return df_display, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# 製造業新訂單總額 (計算 YoY 年增率)
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
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val < danger_threshold
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# 聯準會總資產 (計算 4 週變動率 %)
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
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val > danger_threshold
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# 商業銀行準備金佔聯準會總資產比例 (%)
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
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = current_val < danger_threshold
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# 銅金比 (結合 200 日移動平均線趨勢判斷)
@st.cache_data(ttl=3600)
def get_copper_gold_ratio():
    try:
        cu = yf.Ticker("HG=F").history(start=start_date - pd.DateOffset(days=300), end=end_date)[['Close']]
        au = yf.Ticker("GC=F").history(start=start_date - pd.DateOffset(days=300), end=end_date)[['Close']]
        df = (cu / au).dropna().reset_index()
        df.columns = ['Date', 'Value']
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        
        df['SMA200'] = df['Value'].rolling(window=200).mean()
        df = df[df['Date'] >= start_date].reset_index(drop=True)

        current_val = df['Value'].iloc[-1]
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_sma = df['SMA200'].iloc[-1]
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        
        is_danger = current_val < current_sma
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

# ================= 資料抓取模組 (台灣) =================

@st.cache_data(ttl=3600)
def get_taiwan_historical_volatility(danger_threshold=30.0, is_greater_danger=True):
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
                prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
                current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
                is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
                return df, current_val, prev_val, current_date, is_danger
    except Exception:
        pass
    return pd.DataFrame(), 0, 0, "", False

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
            return pd.DataFrame(), 0, 0, "", False

        current_diff = df['Diff'].iloc[-1]
        prev_diff = df['Diff'].iloc[-2] if len(df) > 1 else current_diff
        current_date = df['Date'].iloc[-1].strftime('%Y/%m')
        is_danger = current_diff < danger_threshold

        return df, current_diff, prev_diff, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

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
            return pd.DataFrame(), 0, 0, "", False

        current_val = df['Value'].iloc[-1]
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m')
        is_danger = current_val < danger_threshold

        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

@st.cache_data(ttl=3600)
def get_usdtwd_data(danger_threshold=33.0, is_greater_danger=True):
    try:
        df = yf.Ticker("TWD=X").history(start=start_date, end=end_date)
        df = df.reset_index()[['Date', 'Close']]
        df.columns = ['Date', 'Value']
        current_val = df['Value'].iloc[-1]
        prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
        current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')
        is_danger = (current_val > danger_threshold) if is_greater_danger else (current_val < danger_threshold)
        return df, current_val, prev_val, current_date, is_danger
    except Exception:
        return pd.DataFrame(), 0, 0, "", False

@st.cache_data(ttl=3600)
def get_taiwan_ma20_bias(overheat_threshold=5.0, breakdown_threshold=-5.0):
    try:
        df_yf = yf.Ticker("^TWII").history(start=start_date, end=end_date).reset_index()
        if not df_yf.empty:
            df_yf['Date'] = pd.to_datetime(df_yf['Date']).dt.tz_localize(None)

            ma20 = df_yf['Close'].rolling(window=20, min_periods=1).mean()
            df_yf['Value'] = ((df_yf['Close'] - ma20) / ma20) * 100.0
            df = df_yf[['Date', 'Value']].dropna().sort_values('Date')

            current_val = df['Value'].iloc[-1]
            prev_val = df['Value'].iloc[-2] if len(df) > 1 else current_val
            current_date = df['Date'].iloc[-1].strftime('%Y/%m/%d')

            status = "normal"
            if current_val > overheat_threshold:
                status = "overheat"
            elif current_val < breakdown_threshold:
                status = "breakdown"

            is_danger = (status == "breakdown")
            return df, current_val, prev_val, current_date, status, is_danger
    except Exception:
        pass

    return pd.DataFrame(), 0, 0, "", "normal", False

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
    tx_val, tx_prev, tx_date, tx_danger = 0, 0, "", False
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
                    tx_prev = df_tx['Value'].iloc[-2] if len(df_tx) > 1 else tx_val
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
    mtx_val, mtx_prev, mtx_date, mtx_danger = 0, 0, "", False
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
                    mtx_prev = df_mtx['Value'].iloc[-2] if len(df_mtx) > 1 else mtx_val
                    mtx_date = df_mtx['Date'].iloc[-1].strftime('%Y/%m/%d')
                    mtx_danger = mtx_val > 10000
    except Exception:
        pass

    return df_tx, tx_val, tx_prev, tx_date, tx_danger, df_mtx, mtx_val, mtx_prev, mtx_date, mtx_danger

# ================= 視覺化繪圖模組 =================

# 核心 6 項採取特製精確切分，輔助 16 項維持標準四分法 (0-4, 4-8, 8-12, 12-16)
def draw_four_color_gauge(danger_count, total_count):
    if total_count == 6:
        step1 = 0.5
        step2 = 1.5
        step3 = 3.5
    else:
        # 輔助景氣籌碼 (16項)：維持均等 25% 四分法
        step1 = 4.0
        step2 = 8.0
        step3 = 12.0

    if danger_count <= step1:
        bar_color = "#2ecc71"
    elif danger_count <= step2:
        bar_color = "#f1c40f"
    elif danger_count <= step3:
        bar_color = "#e67e22"
    else:
        bar_color = "#e74c3c"

    border_style = {'color': '#bdc3c7', 'width': 1.5}

    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = danger_count,
        number = {'suffix': f" / {total_count}", 'font': {'size': 20}},
        gauge = {
            'axis': {
                'range': [0, total_count], 
                'showticklabels': False,  # 隱藏外圍數字刻度
                'ticks': ''               # 隱藏刻度小線條
            },
            'bar': {'color': bar_color, 'thickness': 1.0, 'line': border_style},
            'bgcolor': "#e0e0e0",
            'borderwidth': 1.5,
            'bordercolor': "#bdc3c7",
            'steps': [
                {'range': [0, step1], 'color': '#d4efdf', 'line': border_style},
                {'range': [step1, step2], 'color': '#fcf3cf', 'line': border_style},
                {'range': [step2, step3], 'color': '#fbeee6', 'line': border_style},
                {'range': [step3, total_count], 'color': '#fadbd8', 'line': border_style}
            ]
        }
    ))

    fig.update_layout(
        height=180,
        margin=dict(l=25, r=25, t=15, b=10),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

def draw_line_chart(title, df, is_danger):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            height=200,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
            paper_bgcolor='rgba(0, 0, 0, 0)'
        )
        return fig

    bg_color = 'rgba(255, 235, 235, 1)' if is_danger else 'rgba(255, 255, 255, 1)'
    line_color = 'red' if is_danger else '#1f77b4'

    fig = go.Figure()

    has_legend = "銅金比" in title
    if has_legend and 'SMA200' in df.columns:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Value'], name="銅金比", line=dict(color=line_color, width=2)))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['SMA200'], name="200MA", line=dict(color='gray', width=1.5, dash='dash')))
    else:
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Value'], line=dict(color=line_color, width=2)))

    b_margin = 50 if has_legend else 20
    chart_height = 230 if has_legend else 200

    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=b_margin),
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

def draw_bias_chart(df, status):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            height=200,
            xaxis=dict(showgrid=False, visible=False),
            yaxis=dict(showgrid=False, visible=False),
            paper_bgcolor='rgba(0, 0, 0, 0)'
        )
        return fig

    if status == "breakdown":
        bg_color = 'rgba(255, 235, 235, 1)'
        line_color = 'red'
    elif status == "overheat":
        bg_color = 'rgba(255, 235, 200, 1)'
        line_color = '#e67e22'
    else:
        bg_color = 'rgba(255, 255, 255, 1)'
        line_color = '#1f77b4'

    fig = go.Figure(data=go.Scatter(x=df['Date'], y=df['Value'], line=dict(color=line_color, width=2)))

    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.7)
    fig.add_hline(y=5.0, line_dash="dot", line_color="#e67e22", opacity=0.6)
    fig.add_hline(y=-5.0, line_dash="dot", line_color="red", opacity=0.6)

    fig.update_layout(
        margin=dict(l=20, r=20, t=10, b=20),
        height=200,
        paper_bgcolor=bg_color,
        plot_bgcolor=bg_color,
        uirevision='bias_dataset',
        xaxis=dict(showgrid=False, type='date', autorange=True, tickfont=dict(color='#333333'), fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor='#e0e0e0', autorange=True, fixedrange=True, tickfont=dict(color='#333333'))
    )
    return fig

def draw_m1b_m2_chart(df, is_danger):
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            height=280,
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
            name="M2(年增率,L)",
            line=dict(color="#3498db", width=2)
        ),
        secondary_y=False
    )

    fig.add_trace(
        go.Scatter(
            x=df['Date'],
            y=df['M1B'],
            name="M1B(年增率,L)",
            line=dict(color="#e74c3c", width=2)
        ),
        secondary_y=False
    )

    fig.update_layout(
        height=280,
        margin=dict(l=20, r=20, t=10, b=50),
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

# 格式化數字字串呈現
def format_metric_value(title, val):
    if "銅金比" in title:
        return f"{val:,.4f}"
    elif "維持率" in title or "指標" in title or "年增率" in title or "波動率" in title or "變動率" in title or "準備金佔總資產比" in title or "乖離" in title:
        return f"{val:,.2f}%"
    elif "貼現窗口借款" in title:
        return f"{val:,.0f} 百萬美元"
    elif "外資台指期貨淨未平倉" in title or "散戶小台淨未平倉" in title or "初領失業救濟金" in title:
        return f"{val:,.0f}"
    else:
        return f"{val:,.2f}"

def render_metric_and_chart(title, data_tuple):
    df, current_val, prev_val, current_date, is_danger = data_tuple
    val_str = format_metric_value(title, current_val)
    prev_str = format_metric_value(title, prev_val)
    
    diff = current_val - prev_val
    diff_str = f"{diff:+,.2f}" if "銅金比" not in title else f"{diff:+,.4f}"
    delta_display = f"{diff_str} (前一期: {prev_str}) | 更新日期: {current_date}"
    
    st.metric(
        label=title, 
        value=val_str, 
        delta=delta_display, 
        delta_color="normal"
    )
    st.plotly_chart(draw_line_chart(title, df, is_danger), use_container_width=True, config={'staticPlot': True})
