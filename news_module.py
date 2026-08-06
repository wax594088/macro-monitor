import feedparser
import sqlite3
import urllib.parse

# 定義必須包含的財經核心關鍵字（至少需命中其中一個）
FINANCIAL_KEYWORDS = [
    "台股", "證券", "股市", "金管會", "財經", "央行", "聯準會", 
    "半導體", "科技", "台積電", "美股", "匯率", "經濟", "上市", "上櫃"
]

# 定義絕對要排除的無關雜訊關鍵字（命中任何一個則直接略過）
EXCLUDE_KEYWORDS = [
    "娛樂", "影劇", "星際", "星座", "八卦", "演唱會", "職棒", 
    "中職", "NBA", "電影", "網紅", "藝人", "電視劇", "綜藝"
]

def init_db():
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    # 檢查現有表格的欄位
    cursor.execute("PRAGMA table_info(news)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    
    required_columns = ["id", "url", "title", "source", "published_date", "summary", "importance", "impact_companies", "report_count"]
    
    # 如果表格不存在，或是缺少必要欄位，直接重新建立乾淨的表格
    if not existing_columns or not all(col in existing_columns for col in required_columns):
        cursor.execute("DROP TABLE IF EXISTS news")
        cursor.execute("""
            CREATE TABLE news (
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
        
        # 1. 檢查是否包含排除關鍵字（若包含則直接跳過）
        if any(ex in title for ex in EXCLUDE_KEYWORDS):
            continue
            
        # 2. 檢查是否包含財經核心關鍵字（若完全沒命中則跳過）
        if not any(kw in title for kw in FINANCIAL_KEYWORDS):
            continue
            
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO news (url, title, source, published_date)
                VALUES (?, ?, ?, ?)
            """, (url, title, source, published))
            
            if cursor.rowcount > 0:
                added_count += 1
        except Exception as e:
            print(f"寫入錯誤: {e}")
            
    conn.commit()
    conn.close()
    return added_count

def get_news_from_db(search_query=""):
    init_db()
    conn = sqlite3.connect("news.db")
    cursor = conn.cursor()
    
    if search_query:
        cursor.execute("""
            SELECT published_date, title, source, url, summary, importance, impact_companies, report_count 
            FROM news 
            WHERE title LIKE ? OR source LIKE ?
            ORDER BY id DESC
        """, (f"%{search_query}%", f"%{search_query}%"))
    else:
        cursor.execute("""
            SELECT published_date, title, source, url, summary, importance, impact_companies, report_count 
            FROM news 
            ORDER BY id DESC
        """)
        
    rows = cursor.fetchall()
    conn.close()
    return rows
