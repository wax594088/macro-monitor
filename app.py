import streamlit as st
import datetime
import pandas as pd

# 導入拆分出去的總經模組
import macro_module as mm

# 頁面基礎設定：預設收起側邊欄
st.set_page_config(
    layout="wide", 
    page_title="總體經濟監控系統",
    initial_sidebar_state="collapsed"
)

# 隱藏右上角 Streamlit 原生選單與工具列，設定最適頂部邊距
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# 側邊欄設定
st.sidebar.markdown("### 系統設定")
api_key = st.secrets.get("FRED_API_KEY", "")
finmind_token = st.secrets.get("FINMIND_TOKEN", "")

# 建立分頁 (新增「新聞市況彙整」Tab)
tab_home, tab_analysis, tab_news = st.tabs(["首頁", "產業鏈分析", "新聞市況彙整"])

with tab_home:

    # 1. 抓取 核心流動性與信用危機指標 (6 項)
    stlfsi_data = mm.get_fred_data("STLFSI4", 2.0, True, api_key)
    vix_data = mm.get_fred_data("VIXCLS", 30.0, True, api_key)
    hy_oas_data = mm.get_fred_data("BAMLH0A0HYM2", 6.0, True, api_key)
    baa_data = mm.get_fred_data("BAA10Y", 3.0, True, api_key)
    dcpf3m_data = mm.get_fred_data("DCPF3M", 5.5, True, api_key)
    dpcredit_data = mm.get_fred_data("WPC", 25000, True, api_key)

    core_indicators = [
        ("金融壓力指數 (STLFSI4)", stlfsi_data),
        ("VIX 恐慌指數 (VIXCLS)", vix_data),
        ("高收益債利差 (BAMLH0A0HYM2)", hy_oas_data),
        ("Baa 級企業債利差 (BAA10Y)", baa_data),
        ("金融商業本票利率 (DCPF3M)", dcpf3m_data),
        ("貼現窗口借款 (WPC)", dpcredit_data)
    ]

    # 2. 抓取 輔助景氣與籌碼指標 (16 項)
    walcl_data = mm.get_walcl_change_data(3.0, api_key)
    totresns_data = mm.get_reserve_ratio_data(10.0, api_key)
    icsa_data = mm.get_fred_data("ICSA", 260000, True, api_key)
    t10y2y_data = mm.get_yield_curve_steepening_data("T10Y2Y", api_key)
    t10y3m_data = mm.get_yield_curve_steepening_data("T10Y3M", api_key)
    nosrdisa_data = mm.get_amtmno_yoy_data(0.0, api_key)
    sahm_data = mm.get_fred_data("SAHMREALTIME", 0.5, True, api_key)
    cfnai_data = mm.get_fred_data("CFNAI", -0.7, False, api_key)
    cg_ratio_data = mm.get_copper_gold_ratio()

    twd_data = mm.get_usdtwd_data(33.0, True)
    tw_hv_data = mm.get_taiwan_historical_volatility(30.0, True)
    tw_export_data = mm.get_taiwan_electronics_export_data(0.0)
    tw_m1b_m2_df, tw_m1b_m2_diff, tw_m1b_m2_prev, tw_m1b_m2_date, tw_m1b_m2_danger = mm.get_taiwan_m1b_m2_data(0.0)
    tw_bias_df, tw_bias_val, tw_bias_prev, tw_bias_date, tw_bias_status, tw_bias_danger = mm.get_taiwan_ma20_bias(5.0, -5.0)

    tw_future_oi_df, tw_future_oi_val, tw_future_oi_prev, tw_future_oi_date, tw_future_oi_danger, \
    tw_retail_oi_df, tw_retail_oi_val, tw_retail_oi_prev, tw_retail_oi_date, tw_retail_oi_danger = mm.get_tw_futures_chip(finmind_token)

    tw_future_oi_data = (tw_future_oi_df, tw_future_oi_val, tw_future_oi_prev, tw_future_oi_date, tw_future_oi_danger)
    tw_retail_oi_data = (tw_retail_oi_df, tw_retail_oi_val, tw_retail_oi_prev, tw_retail_oi_date, tw_retail_oi_danger)

    aux_indicators = [
        ("聯準會總資產近月變動率", walcl_data),
        ("商業銀行準備金佔總資產比", totresns_data),
        ("初領失業救濟金", icsa_data),
        ("10Y-2Y 殖利率曲線陡峭化", t10y2y_data),
        ("10Y-3M 殖利率曲線陡峭化", t10y3m_data),
        ("製造業新訂單總額年增率", nosrdisa_data),
        ("薩姆規則衰退指標", sahm_data),
        ("芝加哥全國活動指數", cfnai_data),
        ("銅金比 (含 200SMA)", cg_ratio_data),
        ("美元兌新台幣匯率", twd_data),
        ("財政部電子零組件出口年增率", tw_export_data),
        ("台灣 M1B-M2 剪刀差", (tw_m1b_m2_df, tw_m1b_m2_diff, tw_m1b_m2_prev, tw_m1b_m2_date, tw_m1b_m2_danger)),
        ("大盤月線乖離率", (tw_bias_df, tw_bias_val, tw_bias_prev, tw_bias_date, tw_bias_danger)),
        ("台指期歷史波動率 (20日HV)", tw_hv_data),
        ("外資台指期貨淨未平倉", tw_future_oi_data),
        ("散戶小台淨未平倉", tw_retail_oi_data)
    ]

    core_danger_items = [item for item in core_indicators if item[1][4]]
    aux_danger_items = [item for item in aux_indicators if item[1][4]]

    core_danger_count = len(core_danger_items)
    aux_danger_count = len(aux_danger_items)

    # 雙欄儀表區
    gauge_col, summary_col = st.columns([1, 1])

    with gauge_col:
        st.markdown("#### 📊 風險監控儀表板")
        g1_col, g2_col = st.columns(2)
        with g1_col:
            st.markdown("<p style='text-align: center; font-weight: bold; margin-bottom: 0;'>核心流動性風險</p>", unsafe_allow_html=True)
            st.plotly_chart(mm.draw_four_color_gauge(core_danger_count, 6), use_container_width=True, config={'staticPlot': True})
        with g2_col:
            st.markdown("<p style='text-align: center; font-weight: bold; margin-bottom: 0;'>輔助景氣與籌碼</p>", unsafe_allow_html=True)
            st.plotly_chart(mm.draw_four_color_gauge(aux_danger_count, 16), use_container_width=True, config={'staticPlot': True})

    with summary_col:
        with st.container(border=True):
            st.markdown("#### 🚨 即時警戒摘要清單")
            
            if core_danger_count > 0:
                st.error(f"🔴 **核心流動性發出嚴重警報 ({core_danger_count}/6 項超標)：**")
                for title, data in core_danger_items:
                    st.write(f"• **{title}**：{mm.format_metric_value(title, data[1])} (更新日期: {data[3]})")
            else:
                st.success("🟢 **核心流動性：** 全球金融體系融資與信用正常，無系統性風險。")

            if aux_danger_count > 0:
                st.warning(f"🟡 **輔助景氣與籌碼異常 ({aux_danger_count}/16 項超標)：**")
                for title, data in aux_danger_items:
                    st.write(f"• **{title}**：{mm.format_metric_value(title, data[1])} (更新日期: {data[3]})")
            else:
                st.info("🟢 **輔助景氣與籌碼：** 總體經濟與台股籌碼結構良好。")

    st.divider()

    # 第一層
    st.markdown("### 第一層：全球流動性與信用風險 (美國核心)")
    col1, col2 = st.columns(2)
    with col1:
        mm.render_metric_and_chart("金融壓力指數 (STLFSI4)", stlfsi_data)
        st.markdown("**監控用意：** 監控金融體系流動性與壓力。<br>**判斷方式：** 數值 0 代表歷史平均。大於 0 代表壓力升高。<br>**危機標準：** 數值快速攀升並突破 2.0。", unsafe_allow_html=True)
    with col2:
        mm.render_metric_and_chart("VIX 恐慌指數 (VIXCLS)", vix_data)
        st.markdown("**監控用意：** 監控市場恐慌情緒與波動預期。<br>**判斷方式：** 數值急升代表市場避險情緒飆高。<br>**危機標準：** 數值突破 30 為實質恐慌。", unsafe_allow_html=True)

    st.write("---")

    col3, col4 = st.columns(2)
    with col3:
        mm.render_metric_and_chart("高收益債利差 (BAMLH0A0HYM2)", hy_oas_data)
        st.markdown("**監控用意：** 衡量市場風險偏好與高風險企業違約機率。<br>**判斷方式：** 利差飆升代表機構大舉拋售高風險資產。<br>**危機標準：** 利差突破 6.0% 代表避險情緒升溫。", unsafe_allow_html=True)
    with col4:
        mm.render_metric_and_chart("Baa 級企業債利差 (BAA10Y)", baa_data)
        st.markdown("**監控用意：** 監控中等信用評級企業的融資成本與壓力。<br>**判斷方式：** 利差擴大代表實體企業籌資困難。<br>**危機標準：** 利差快速飆升並突破 3.0%。", unsafe_allow_html=True)

    st.write("---")

    col5, col6 = st.columns(2)
    with col5:
        mm.render_metric_and_chart("金融商業本票利率 (DCPF3M)", dcpf3m_data)
        st.markdown("**監控用意：** 監控企業短期無擔保融資成本。<br>**判斷方式：** 利率高檔攀升代表企業借貸成本增加。<br>**危機標準：** 利率絕對值突破 5.5% 反映融資壓力高漲。", unsafe_allow_html=True)
    with col6:
        mm.render_metric_and_chart("貼現窗口借款 (DPCREDIT)", dpcredit_data)
        st.markdown("**監控用意：** 監控銀行體系應對緊急流動性缺口之需求。<br>**判斷方式：** 正常情況下借款金額趨近於零。<br>**危機標準：** 借款規模突破 25,000 百萬美元，反映金融機構出現極端流動性危機。", unsafe_allow_html=True)

    st.divider()

    # 第二層
    st.markdown("### 第二層：台灣基本面與資金流向")
    tw_fund1, tw_fund2 = st.columns(2)
    with tw_fund1:
        mm.render_metric_and_chart("財政部電子零組件出口年增率", tw_export_data)
        st.markdown("**監控用意：** 預判台股半導體與科技業基本面轉折。<br>**判斷方式：** 趨勢領先台股科技企業營收約 1 至 2 個月。<br>**危機標準：** 年增率高檔轉折反轉，或跌破 0.0% 進入產業收縮期。", unsafe_allow_html=True)
    with tw_fund2:
        mm.render_metric_and_chart("美元兌新台幣匯率 (USD/TWD)", twd_data)
        st.markdown("**監控用意：** 監控外資資金進出台股動向與匯率風險。<br>**判斷方式：** 台幣貶值通常伴隨外資賣超台股。<br>**危機標準：** 台幣短時間內急速貶值並突破關鍵整數防線（33.0）。", unsafe_allow_html=True)

    st.write("---")

    tw_m1b_m2_diff_str = f"{tw_m1b_m2_diff - tw_m1b_m2_prev:+,.2f}% (前一期: {tw_m1b_m2_prev:,.2f}%) | 更新日期: {tw_m1b_m2_date}"
    st.metric(label="台灣-M1B vs. M2 (剪刀差)", value=f"{tw_m1b_m2_diff:,.2f}%", delta=tw_m1b_m2_diff_str, delta_color="normal")
    st.plotly_chart(mm.draw_m1b_m2_chart(tw_m1b_m2_df, tw_m1b_m2_danger), use_container_width=True, config={'staticPlot': True})
    st.markdown("**監控用意：** 衡量國內股市資金動態與流動性。<br>**判斷方式：** M1B 年增率大於 M2 屬資金動能充沛。<br>**危機標準：** M1B 年增率急遽下滑並由上往下穿透 M2（死亡交叉）。", unsafe_allow_html=True)

    st.divider()

    # 第三層
    st.markdown("### 第三層：美總體景氣與衰退預警 (中長期觀察)")
    col11, col12 = st.columns(2)
    with col11:
        mm.render_metric_and_chart("10年減2年期利差 (T10Y2Y)", t10y2y_data)
        st.markdown("**監控用意：** 評估中長期經濟衰退風險與殖利率曲線型態。<br>**判斷方式：** 過去半年間曾倒掛，且近 1 個月急劇向上陡峭化轉正。<br>**危機標準：** 深度倒掛後急速拉升轉正（反映衰退降臨與降息循環啟動）。", unsafe_allow_html=True)
    with col12:
        mm.render_metric_and_chart("10年減3個月期利差 (T10Y3M)", t10y3m_data)
        st.markdown("**監控用意：** 聯準會最看重的衰退預警指標。<br>**判斷方式：** 過去半年間曾倒掛，且近 1 個月急劇向上陡峭化轉正。<br>**危機標準：** 深度倒掛後急速拉升轉正。", unsafe_allow_html=True)

    st.write("---")

    col13, col14 = st.columns(2)
    with col13:
        mm.render_metric_and_chart("製造業新訂單總額年增率 (AMTMNO)", nosrdisa_data)
        st.markdown("**監控用意：** 預判製造業擴張或收縮之領先指標。<br>**判斷方式：** 觀察新訂單總額之年對年成長動能。<br>**危機標準：** 年增率 (YoY) 跌破 0.0% 反映製造業進入收縮期。", unsafe_allow_html=True)
    with col14:
        mm.render_metric_and_chart("薩姆規則 (SAHMREALTIME)", sahm_data)
        st.markdown("**監控用意：** 即時判定經濟是否已步入衰退。<br>**判斷方式：** 計算失業率移動平均值與低點差值。<br>**危機標準：** 差值突破 0.5 個百分點。", unsafe_allow_html=True)

    st.write("---")

    col15, col16 = st.columns(2)
    with col15:
        mm.render_metric_and_chart("芝加哥全國活動指數 (CFNAI)", cfnai_data)
        st.markdown("**監控用意：** 綜合評估整體經濟活動成長率。<br>**判斷方式：** 小於 0 為低於歷史趨勢。<br>**危機標準：** 三個月移動平均值跌破 -0.7。", unsafe_allow_html=True)
    with col16:
        mm.render_metric_and_chart("銅金比 (含200SMA)", cg_ratio_data)
        st.markdown("**監控用意：** 衡量市場風險偏好與景氣擴張力道。<br>**判斷方式：** 當前數值低於 200 日均線（SMA）代表實體需求弱化且避險情緒升溫。<br>**危機標準：** 銅金比跌破 200 日均線趨勢向下。", unsafe_allow_html=True)

    st.write("---")

    col17, col18 = st.columns(2)
    with col17:
        mm.render_metric_and_chart("聯準會總資產近月變動率 (WALCL)", walcl_data)
        st.markdown("**監控用意：** 監測聯準會資產負債表擴張狀態。<br>**判斷方式：** 變動率急升代表央行介入救市或發生流動性危機的同步確認訊號。<br>**危機標準：** 近 4 週資產規模變動率突破 +3.0%。", unsafe_allow_html=True)
    with col18:
        mm.render_metric_and_chart("商業銀行準備金佔總資產比 (TOTRESNS/WALCL)", totresns_data)
        st.markdown("**監控用意：** 監測美國銀行體系的基礎流動性充裕程度。<br>**判斷方式：** 準備金占美聯儲資產比例下滑代表金融體系流動性抽離。<br>**危機標準：** 比率跌破 10.0%，反映銀行體系流動性水位降至緊縮警戒區。", unsafe_allow_html=True)

    st.write("---")

    col19, col20 = st.columns(2)
    with col19:
        mm.render_metric_and_chart("初領失業救濟金 (ICSA)", icsa_data)
        st.markdown("**監控用意：** 監控勞動力市場短期動能與裁員狀況。<br>**判斷方式：** 趨勢持續向上代表企業加速裁員。<br>**危機標準：** 數值連續數週突破 26 萬人，反映就業市場明顯惡化。", unsafe_allow_html=True)
    with col20:
        st.write("")

    st.divider()

    # 第四層
    st.markdown("### 第四層：台股短線籌碼與技術面 (同步與落後指標)")
    tw_chip1, tw_chip2 = st.columns(2)
    with tw_chip1:
        mm.render_metric_and_chart("台指期歷史波動率 (20日HV)", tw_hv_data)
        st.markdown("**監控用意：** 監控台股大盤短線價格真實劇烈變動程度。<br>**判斷方式：** 數值急升代表台股大盤短線走勢轉趨劇烈。<br>**危機標準：** 年化歷史波動率突破 30.0% 進入高風險狀態。", unsafe_allow_html=True)
    with tw_chip2:
        tw_bias_diff_str = f"{tw_bias_val - tw_bias_prev:+,.2f}% (前一期: {tw_bias_prev:,.2f}%) | 更新日期: {tw_bias_date}"
        st.metric(label="大盤乖離冷熱指標", value=f"{tw_bias_val:,.2f}%", delta=tw_bias_diff_str, delta_color="normal")
        st.plotly_chart(mm.draw_bias_chart(tw_bias_df, tw_bias_status), use_container_width=True, config={'staticPlot': True})
        st.markdown("**監控用意：** 觀察台股大盤相對於月線（20MA）的價格偏離程度，判定短線過熱或乖離過大。<br>**判斷方式：** 0% 為基準線。高於 +5% 短線過熱；低於 -5% 短線超賣乖離過大。<br>**危機標準：** 跌破 -5.0% 反映短線價格結構轉弱與修正壓力。", unsafe_allow_html=True)

    st.write("---")

    tw_chip3, tw_chip4 = st.columns(2)
    with tw_chip3:
        mm.render_metric_and_chart("外資台指期貨淨未平倉", tw_future_oi_data)
        st.markdown("**監控用意：** 觀察外資對台股大盤的避險與方向性布局。<br>**判斷方式：** 需結合現貨買賣超觀察，若期貨淨空單急遽累積且現貨大賣，代表實質看空。<br>**危機標準：** 淨空單大量累積突破 45,000 口且現貨同步賣超。", unsafe_allow_html=True)
    with tw_chip4:
        mm.render_metric_and_chart("散戶小台淨未平倉", tw_retail_oi_data)
        st.markdown("**監控用意：** 觀察市場散戶槓桿部位，作為極端行情的反指標。<br>**判斷方式：** 大盤下跌時散戶淨多單快速累積追跌抄底，代表籌碼沉澱不良，易引發多頭踩踏。<br>**危機標準：** 散戶淨多單異常激增（突破 10,000 口）且大盤持續破底。", unsafe_allow_html=True)

with tab_analysis:
    st.write("產業鏈分析模組建置中...")

with tab_news:
    st.write("新聞市況彙整模組建置中...")
