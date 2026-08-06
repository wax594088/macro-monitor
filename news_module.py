import feedparser
import sqlite3
import urllib.parse
import os
from google import genai  # 假設您使用 Google GenAI SDK

FINANCIAL_KEYWORDS = [
    "台股", "證券", "股市", "金管會", "財經", "央行", "聯準會", 
    "半導體", "科技", "台積電", "美股", "匯率", "經濟", "上市", "上櫃", "AI"
]

EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝"
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
            importance TEXT, -- 填入 🔴高、🟡中、⚪低
            impact_companies TEXT, -- 僅顯示對應台股
            report_count INTEGER DEFAULT 1
        )
    """)
    
    # 檢查並補齊可能缺少的欄位
    existing_columns = [row[1] for row in cursor.execute("PRAGMA table_info(news)").fetchall()]
    cols_to_add = {
        "summary": "TEXT",
        "importance": "TEXT",
        "impact_companies": "TEXT",
        "report_count": "INTEGER DEFAULT 1"
    }
    for col, col_type in cols_to_add.items():
        if col not in existing_columns:
            cursor.execute(f"ALTER TABLE news ADD COLUMN {col} {col_type}")
            
    conn.commit()
    conn.close()

def analyze_news_with_ai(title, source):
    """透過 AI 將新聞轉化為結構化資訊，並僅對應台股"""
    # 若您沒有設定 API Key，可先回傳預設值避免報錯
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "尚未設定 AI 金鑰，無法產生摘要。", "⚪ 低", "無"
        
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    你是一個專業的台股財經分析師。請根據以下新聞標題與來源，進行結構化分析：
    新聞標題：{title}
    新聞來源：{source}

    請嚴格依照下列格式回傳，不要有多餘廢話：
    摘要：[用一到兩句簡短說明事件核心與市場影響]
    重要性：[請填 🔴高、🟡中、或 ⚪低 其中之一]
    影響台股：[列出受此事件影響的台股公司名稱與代號，例如：台積電(2330)、聯發科(2454)。若完全無關台股請填「無」]
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        text = response.text.strip()
        
        # 簡單解析 AI 回傳的文字
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

def fetch_and_store_news(query="台股"):
    init_db()
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    
    feed = feedparser.parse(rss_url)
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    added_count = 0
    
    for entry in feed.entries:
        title = entry.title
        url = entry.link
        source = entry.get('source', {}).get('title', '未知來源')
        published = entry.get('published', '')
        
        if any(ex in title for ex in EXCLUDE_KEYWORDS):
            continue
        if not any(kw in title for kw in FINANCIAL_KEYWORDS):
            continue
            
        # 檢查網址是否已存在
        cursor.execute("SELECT id, report_count FROM news WHERE url = ?", (url,))
        existing = cursor.fetchone()
        
        if existing:
            # 若網址已存在，不重複新增
            continue
            
        # 呼叫 AI 進行結構化萃取
        summary, importance, impact_companies = analyze_news_with_ai(title, source)
        
        try:
            cursor.execute("""
                INSERT INTO news (url, title, source, published_date, summary, importance, impact_companies, report_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (url, title, source, published, summary, importance, impact_companies))
            added_count += 1
        except Exception as e:
            print(f"寫入錯誤: {e}")
            
    conn.commit()
    conn.close()
    return added_count

def get_news_from_db(search_query="", limit=30, importance_filter=None, sort_by="時間新到舊"):
    init_db()
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    sql = """
        SELECT published_date, title, source, url, summary, importance, impact_companies, report_count 
        FROM news 
        WHERE 1=1
    """
    params = []
    
    if search_query:
        sql += " AND (title LIKE ? OR source LIKE ? OR impact_companies LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
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
