import feedparser
import sqlite3
import urllib.parse
import os
import re
from collections import Counter
from groq import Groq
from email.utils import parsedate_to_datetime
import datetime

# 強制設定台灣台北時區 (UTC+8)
TZ_TAIPEI = datetime.timezone(datetime.timedelta(hours=8))

EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝",
    "定期定額", "小資族", "新手", "教學", "開戶", "ETF掛牌",
    "存股", "理財", "買房", "租屋", "信用卡", "現金回饋", "保險",
    "退休", "省錢", "發票", "中獎", "運勢", "生肖",
    "飼主", "寵物", "鄰居", "社會", "車禍", "命案", "外送", "勞基法"
]

def clean_old_news():
    try:
        conn = sqlite3.connect("news.db")
        cursor = conn.cursor()
        cutoff_date = (datetime.datetime.now(TZ_TAIPEI) - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
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
        dt_taipei = dt.astimezone(TZ_TAIPEI)
        return dt_taipei.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return datetime.datetime.now(TZ_TAIPEI).strftime("%Y-%m-%d %H:%M:%S")

def clean_title_for_comparison(title):
    """去除新聞標題尾端的媒體名稱與符號，用於比對是否為同新聞議題"""
    cleaned = re.sub(r' - [^-]+$', '', title)
    cleaned = re.sub(r'[\s\s\t\n\r]', '', cleaned)
    return cleaned[:15]  # 取前15個關鍵字進行核心特徵比對

def generate_dynamic_queries():
    api_key = os.environ.get("GROQ_API_KEY")
    
    if api_key:
        try:
            fallback_url = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            feed = feedparser.parse(fallback_url)
            realtime_headlines = [entry.title for entry in feed.entries[:30]]
            headlines_text = "\n".join(realtime_headlines) if realtime_headlines else "近期台股科技、半導體、政策與總經動態"

            client = Groq(api_key=api_key)
            prompt = f"""
            以下是今天從市場即時抓取的新聞標題：
            {headlines_text}

            你是一個專業的台股操盤手。請從上述真實標題中，嚴格篩選並歸納出 3 個「最具市場熱度、具備具體公司、產業或政策動向」的精確搜尋短字串。
            絕對禁止產出空泛或與股市無關的詞彙。
            請嚴格只回傳 3 個搜尋短字串，每行一個，不要有編號或額外文字。
            """
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2
            )
            text = response.choices[0].message.content.strip()
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if lines:
                return lines[:3], "動態關鍵字產生成功 (AI 結合即時市場熱點)"
        except Exception:
            pass 

    return [""], "AI 額度已滿，切換至「三大專業財經媒體直抓備援機制」"

def analyze_news_with_ai(title, source):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return fallback_rule_analysis(title)
        
    try:
        client = Groq(api_key=api_key)
        prompt = f"""
        你是一個專業的台股操盤手。請評估以下新聞是否具備實質影響台股股價或產業預期的潛力：
        新聞標題：{title}
        新聞來源：{source}

        判斷標準：
        - 若屬於一般理財、生活消費、社會新聞、寵物、無具體公司財報/訂單的小道消息、或與台股無關，請將重要性設為「⚪ 低」。
        - 若屬於核心維度（政策紅利、突發風險、基本面拐點、總經變數、供應鏈衝擊），請將重要性設為「🔴 高」或「🟡 中」。

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
        
        summary, importance, impact_companies = "", "⚪ 低", ""
        for line in text.split("\n"):
            if "摘要：" in line:
                summary = line.replace("摘要：", "").strip()
            elif "重要性：" in line:
                importance = line.replace("重要性：", "").strip()
            elif "影響台股：" in line:
                val = line.replace("影響台股：", "").strip()
                if val != "無":
                    impact_companies = val
                
        return summary, importance, impact_companies, 1
    except Exception:
        return fallback_rule_analysis(title)

def fallback_rule_analysis(title):
    financial_terms = ["股", "市", "營收", "財報", "獲利", "半導體", "科技", "金管會", "央行", "指數", "供應鏈", "大單", "法人", "外資", "上市", "櫃", "重訊"]
    has_finance_keyword = any(term in title for term in financial_terms)
    
    if not has_finance_keyword:
        return "", "⚪ 低", "", 0

    match = re.search(r'([\u4e00-\u9fa5\w]+)\((\d{4})\)', title)
    if match:
        matched = f"{match.group(1)}({match.group(2)})"
    else:
        stock_map = {
            "台積電": "台積電(2330)", "鴻海": "鴻海(2317)", "聯發科": "聯發科(2454)",
            "廣達": "廣達(2382)", "台達電": "台達電(2308)", "聯電": "聯電(2303)",
            "緯創": "緯創(3231)", "緯穎": "緯穎(6669)", "技嘉": "技嘉(2376)",
            "科懋": "科懋(6496)", "寶島科": "寶島科(5312)", "凌華": "凌華(6166)",
            "台塑": "台塑(1301)", "南亞": "南亞(1303)", "台化": "台化(1326)",
            "中華電": "中華電(2412)", "國泰金": "國泰金(2882)", "富邦金": "富邦金(2881)"
        }
        matched = ""
        for k, v in stock_map.items():
            if k in title:
                matched = v
                break
    return "", "🟡 中", matched, 0

def fetch_and_store_news():
    init_db()
    logs = []
    
    target_queries, query_status = generate_dynamic_queries()
    logs.append(f"【步驟一】關鍵字狀態：{query_status}")
    
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    added_count = 0
    total_fetched = 0
    
    media_filter = "site:ctee.com.tw OR site:edn.udn.com OR site:cnyes.com"
    
    for q in target_queries:
        if q.strip():
            query_with_time = f"{q} ({media_filter}) when:3d"
            log_query_name = f"關鍵字「{q}」"
        else:
            query_with_time = f"({media_filter}) when:3d"
            log_query_name = "三大財經媒體全量直抓"

        encoded_query = urllib.parse.quote(query_with_time)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        total_fetched += len(feed.entries)
        
        logs.append(f"【步驟二】模式：{log_query_name} (時間：近三天) 抓取到原始新聞：{len(feed.entries)} 篇")
        
        for entry in feed.entries:
            title = entry.title
            url = entry.link
            source = entry.get('source', {}).get('title', '未知來源')
            raw_published = entry.get('published', '')
            published = parse_pub_date(raw_published)
            
            if any(ex in title for ex in EXCLUDE_KEYWORDS):
                continue
                
            # 1. 檢查完全相同的網址
            cursor.execute("SELECT id FROM news WHERE url = ?", (url,))
            if cursor.fetchone():
                continue

            # 2. 標題相近查重與曝光次數（report_count）累加
            core_title_keyword = clean_title_for_comparison(title)
            cursor.execute("SELECT id, report_count FROM news WHERE title LIKE ?", (f"%{core_title_keyword}%",))
            existing = cursor.fetchone()
            
            if existing:
                news_id, current_count = existing
                cursor.execute("UPDATE news SET report_count = report_count + 1 WHERE id = ?", (news_id,))
                continue
                
            # 3. 若為新議題，則解析並寫入資料庫
            summary, importance, impact_companies, is_ai = analyze_news_with_ai(title, source)
            
            if importance == "⚪ 低":
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
    logs.append(f"【步驟三】總共處理原始文章 {total_fetched} 篇，成功寫入近三日高價值情報 {added_count} 筆。")
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
