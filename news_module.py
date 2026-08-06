import feedparser
import sqlite3
import urllib.parse
import os
from google import genai

EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶", "ETF掛牌"
]

def init_db():
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            source TEXT,
            published_date TEXT,
            summary TEXT,
            importance TEXT,
            impact_companies TEXT,
            report_count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def generate_dynamic_queries():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return ["台股 營收 突破", "產業 政策 供應鏈"], "未偵測到 GEMINI_API_KEY 環境變數"
        
    try:
        client = genai.Client(api_key=api_key)
        prompt = """
        你是一個專業的台股操盤手。請根據當前最新市場動態，隨機或依據熱點發想 3 個最適合用來搜尋當前市場重大事件、政策紅利、供應鏈變數或突發風險的短字串（例如：「半導體 擴產 訂單」、「國防預算 政策」、「央行 升息 總經」）。
        請嚴格只回傳 3 個搜尋短字串，每行一個，不要有編號或額外文字。
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        lines = [line.strip() for line in response.text.strip().split("\n") if line.strip()]
        queries = lines[:3] if lines else ["台股 營收 突破", "產業 政策 供應鏈"]
        return queries, "動態關鍵字產生成功"
    except Exception as e:
        return ["台股 營收 突破", "產業 政策 供應鏈"], f"動態關鍵字產生失敗: {e}"

def analyze_news_with_ai(title, source):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "尚未設定 AI 金鑰。", "⚪ 低", "無"
        
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        你是一個專業的台股操盤手。請評估以下新聞是否具備影響市場預期或股價的潛力：
        新聞標題：{title}
        新聞來源：{source}

        判斷標準：
        - 若屬於例行公告、理財教育、無實質利多利空的小道消息、或與台股無關，請將重要性設為「⚪ 低」。
        - 若屬於「政府政策/預算紅利、企業重大訂單/拐點、突發調查/訴訟風險、財報大幅超乎預期、總體經濟重大變數、供應鏈瓶頸衝擊」，請將重要性設為「🔴 高」或「🟡 中」。

        請嚴格依照下列格式回傳：
        摘要：[用一句話精準說明事件本質與市場影響]
        重要性：[請填 🔴高、🟡中、或 ⚪低]
        影響台股：[列出受此事件影響的台股公司名稱與代號，例如：台積電(2330)。若非高價值事件或無關台股請填「無」]
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        
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
        return f"AI 解析失敗: {e}", "⚪ 低", "無"

def fetch_and_store_news():
    init_db()
    logs = []
    
    target_queries, query_status = generate_dynamic_queries()
    logs.append(f"【步驟一】關鍵字狀態：{query_status}")
    logs.append(f"【步驟一】使用的搜尋詞：{target_queries}")
    
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    added_count = 0
    total_fetched = 0
    
    for q in target_queries:
        encoded_query = urllib.parse.quote(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        total_fetched += len(feed.entries)
        logs.append(f"【步驟二】搜尋詞「{q}」抓取到原始新聞：{len(feed.entries)} 篇")
        
        for entry in feed.entries:
            title = entry.title
            url = entry.link
            source = entry.get('source', {}).get('title', '未知來源')
            published = entry.get('published', '')
            
            if any(ex in title for ex in EXCLUDE_KEYWORDS):
                continue
                
            cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
            if cursor.fetchone():
                continue
                
            summary, importance, impact_companies = analyze_news_with_ai(title, source)
            
            if importance == "⚪ 低" and impact_companies == "無":
                continue
                
            try:
                cursor.execute("""
                    INSERT INTO news (url, title, source, published_date, summary, importance, impact_companies, report_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (url, title, source, published, summary, importance, impact_companies))
                added_count += 1
            except Exception as e:
                logs.append(f"寫入資料庫錯誤: {e}")
                
    conn.commit()
    conn.close()
    logs.append(f"【步驟三】總共處理原始文章 {total_fetched} 篇，成功寫入高價值情報 {added_count} 筆。")
    return added_count, logs

def get_news_from_db(search_query="", limit=30, importance_filter=None, sort_by="時間新到舊"):
    init_db()
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    sql = "SELECT published_date, title, source, url, summary, importance, impact_companies, report_count FROM news WHERE 1=1"
    params = []
    
    if search_query:
        sql += " AND (title LIKE ? OR source LIKE ? OR impact_companies LIKE ? OR summary LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
    if importance_filter:
        sql += " AND importance LIKE ?"
        params.append(f"%{importance_filter}%")
        
    if sort_by == "重要性優先":
        sql += " ORDER BY CASE WHEN importance LIKE '%🔴%' THEN 1 WHEN importance LIKE '%🟡%' THEN 2 ELSE 3 END ASC, id DESC"
    else:
        sql += " ORDER BY id DESC"
        
    sql += " LIMIT ?"
    params.append(limit)
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
