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
            report_count INTEGER DEFAULT 1,
            is_ai INTEGER DEFAULT 1
        )
    """)
    try:
        cursor.execute("ALTER TABLE news ADD COLUMN is_ai INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass
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
    
    if api_key:
        try:
            fallback_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            feed = feedparser.parse(fallback_url)
            realtime_headlines = [entry.title for entry in feed.entries[:25]]
            headlines_text = "\n".join(realtime_headlines) if realtime_headlines else "近期台股科技、半導體、政策與總經動態"

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

    return [
        "台股 半導體 營收 供應鏈",
        "金管會 政策 產業 影響",
        "上市 櫃 公司 重訊 獲利"
    ], "動態關鍵字產生失敗 (已切換至專業台股財經備援關鍵字)"

def analyze_news_with_ai(title, source):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "", "⚪ 低", "無", 0
        
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
        
        summary, importance, impact_companies = "", "⚪ 低", "無"
        for line in text.split("\n"):
            if "摘要：" in line:
                summary = line.replace("摘要：", "").strip()
            elif "重要性：" in line:
                importance = line.replace("重要性：", "").strip()
            elif "影響台股：" in line:
                impact_companies = line.replace("影響台股：", "").strip()
                
        return summary, importance, impact_companies, 1
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "rate_limit" in error_str.lower():
            # 1. 優先檢查標題是否自帶括號代號格式
            match = re.search(r'([\u4e00-\u9fa5\w]+)\((\d{4})\)', title)
            if match:
                matched = f"{match.group(1)}({match.group(2)})"
            else:
                # 2. 若未帶代號，透過擴充的對應字典進行名稱比對自動補上代號
                stock_map = {
                    "台積電": "台積電(2330)", "鴻海": "鴻海(2317)", "聯發科": "聯發科(2454)",
                    "廣達": "廣達(2382)", "台達電": "台達電(2308)", "聯電": "聯電(2303)",
                    "緯創": "緯創(3231)", "緯穎": "緯穎(6669)", "技嘉": "技嘉(2376)",
                    "科懋": "科懋(6496)", "寶島科": "寶島科(5312)", "凌華": "凌華(6166)",
                    "台塑": "台塑(1301)", "南亞": "南亞(1303)", "台化": "台化(1326)",
                    "中華電": "中華電(2412)", "國泰金": "國泰金(2882)", "富邦金": "富邦金(2881)"
                }
                matched = "無"
                for k, v in stock_map.items():
                    if k in title:
                        matched = v
                        break
            return "", "🟡 中", matched, 0
            
        return "", "⚪ 低", "無", 0

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
                
            summary, importance, impact_companies, is_ai = analyze_news_with_ai(title, source)
            
            if importance == "⚪ 低" or (impact_companies == "無" and is_ai == 1):
                continue
                
            try:
                cursor.execute("""
                    INSERT INTO news (url, title, source, published_date, summary, importance, impact_companies, report_count, is_ai)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (url, title, source, published, summary, importance, impact_companies, is_ai))
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
    
    sql = "SELECT published_date, title, source, url, summary, importance, impact_companies, report_count, is_ai FROM news WHERE 1=1"
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
