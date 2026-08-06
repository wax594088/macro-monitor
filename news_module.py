import feedparser
import sqlite3
import urllib.parse
import os
import re
from collections import Counter
from groq import Groq
from email.utils import parsedate_to_datetime
import datetime

EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶", "ETF掛牌",
    "存股", "理財", "買房", "租屋", "信用卡", "現金回饋", "保險",
    "退休", "省錢", "發票", "中獎", "運勢", "生肖"
]

def clean_old_news():
    try:
        conn = sqlite3.connect("news.db")
        cursor = conn.cursor()
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM news WHERE published_date < ?", (cutoff_date,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def clear_all_news():
    try:
        conn = sqlite3.connect("news.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM news")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

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
    clean_old_news()

def parse_pub_date(published_str):
    try:
        dt = parsedate_to_datetime(published_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def generate_dynamic_queries():
    api_key = os.environ.get("GROQ_API_KEY")
    
    # 【步驟一】先由程式主動抓取 Google 財經即時頭條標題作為市場真實背景
    realtime_headlines = []
    try:
        fallback_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(fallback_url)
        realtime_headlines = [entry.title for entry in feed.entries[:25]]
    except Exception:
        pass

    headlines_text = "\n".join(realtime_headlines) if realtime_headlines else "近期台股科技、半導體、政策與總經動態"

    # 【步驟二】當 API 額度正常時，將即時標題餵給 AI，讓 AI 從中精選與對應熱點
    if api_key:
        try:
            client = Groq(api_key=api_key)
            prompt = f"""
            以下是今天從市場即時抓取的新聞標題：
            {headlines_text}

            你是一個專業的台股操盤手。請從上述真實標題與以下 5 大核心維度中，綜合歸納出 3 個最能對應當前盤勢熱點的精確搜尋短字串：
            1. 政策與預算紅利（政府重大採購、國防預算、法案或補貼）
            2. 突發風險與變故（企業調查、訴訟、重訊或經營權變動）
            3. 基本面拐點與大單（大單傳聞、併購案、財報超預期）
            4. 總體經濟變數（通膨、就業、央行利率決議）
            5. 供應鏈衝擊（斷鏈、短缺、原物料價格波動）

            請嚴格只回傳 3 個搜尋短字串，每行一個，不要有編號或額外文字。
            """
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            text = response.choices[0].message.content.strip()
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if lines:
                return lines[:3], "動態關鍵字產生成功 (AI 結合即時市場熱點)"
        except Exception:
            pass 

    # 【步驟三】若 AI 呼叫失敗或額度滿，退回純高頻詞統計備援
    try:
        if realtime_headlines:
            words = []
            stopwords = {"的", "股", "市", "與", "在", "等", "台", "美", "日", "月", "年", "將", "要", "受", "喊", "創", "高", "低", "飆", "跌"}
            for t in realtime_headlines:
                clean_t = re.sub(r'[^\w\s]', '', t)
                for i in range(len(clean_t) - 1):
                    w = clean_t[i:i+2]
                    if w not in stopwords and not w.isdigit():
                        words.append(w)
            common_words = [item[0] for item in Counter(words).most_common(10)]
            if len(common_words) >= 6:
                return [
                    f"{common_words[0]} {common_words[1]}",
                    f"{common_words[2]} {common_words[3]}",
                    f"{common_words[4]} {common_words[5]}"
                ], "動態關鍵字產生成功 (熱點高頻詞萃取備援)"
    except Exception:
        pass

    return ["台股 營收 突破", "產業 政策 供應鏈"], "動態關鍵字產生失敗 (使用預設)"

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
            return f"AI 額度已滿，改由系統自動篩選：{title}", "🟡 中", "台股相關產業"
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
        query_with_time = f"{q} when:14d"
        encoded_query = urllib.parse.quote(query_with_time)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        total_fetched += len(feed.entries)
        logs.append(f"【步驟二】搜尋詞「{q} (近兩週)」抓取到原始新聞：{len(feed.entries)} 篇")
        
        for entry in feed.entries:
            title = entry.title
            url = entry.link
            source = entry.get('source', {}).get('title', '未知來源')
            raw_published = entry.get('published', '')
            published = parse_pub_date(raw_published)
            
            if any(ex in title for ex in EXCLUDE_KEYWORDS):
                continue
                
            cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
            if cursor.fetchone():
                continue
                
            summary, importance, impact_companies = analyze_news_with_ai(title, source)
            
            if importance == "⚪ 低" or impact_companies == "無" or not impact_companies:
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
        sql += " ORDER BY CASE WHEN importance LIKE '%🔴%' THEN 1 WHEN importance LIKE '%🟡%' THEN 2 ELSE 3 END ASC, published_date DESC"
    else:
        sql += " ORDER BY published_date DESC"
        
    sql += " LIMIT ?"
    params.append(limit)
    
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    return rows
