def analyze_news_with_ai(title, source):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "尚未設定 AI 金鑰。", "⚪ 低", "無"
        
    try:
        client = Groq(api_key=api_key)
        prompt = f"""
        你是一個專業的台股操盤手。請評估以下新聞是否具備實質影響台股股價或產業預期的潛力：
        新聞標題：{title}
        新聞來源：{source}

        判斷標準：
        - 若屬於一般理財、生活消費、無具體公司財報/訂單的小道消息、或與台股無關，請將重要性設為「⚪ 低」。
        - 若屬於 5 大核心維度（政策紅利、突發風險、基本面拐點、總經變數、供應鏈衝擊），請將重要性設為「🔴 高」或「🟡 中」。

        請嚴格依照下列格式回傳：
        摘要：[用一句話精準說明事件本質與市場影響]
        重要性：[請填 🔴高、🟡中、或 ⚪低]
        影響台股：[必須明確列出受此事件影響的台股公司名稱與代號，例如：台積電(2330)。若無法明確對應具體台股代號或屬低價值新聞，請填「無」]
        """
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        text = response.choices[0].message.content.strip()
        
        summary, importance, impact_companies = "無摘要", "⚪ 低", "無"
        for line in text.split("\n"):
            if "摘要：" in line:
                summary = line.replace("摘要：", "").strip()
            elif "重要性：" in line:
                importance = line.replace("重要性：", "").strip()
            elif "影響台股：" in line:
                impact_companies = line.replace("影響台股：", "").strip()
                
        return summary, importance, impact_companies
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "rate_limit" in error_str.lower():
            # 【智慧備援】當 AI 額度滿時，從標題直接對應常見台股代號
            stock_map = {
                "台積電": "台積電(2330)", "鴻海": "鴻海(2317)", "聯發科": "聯發科(2454)",
                "廣達": "廣達(2382)", "台達電": "台達電(2308)", "聯電": "聯電(2303)",
                "緯創": "緯創(3231)", "緯穎": "緯穎(6669)", "技嘉": "技嘉(2376)",
                "半導體": "半導體類股", "AI": "台股AI概念股"
            }
            matched = "台股供應鏈"
            for k, v in stock_map.items():
                if k in title:
                    matched = v
                    break
            return f"AI 額度已滿，改由系統自動篩選：{title}", "🟡 中", matched
            
        return f"AI 解析失敗: {e}", "⚪ 低", "無"
