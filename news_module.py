import sqlite3
import feedparser
from datetime import datetime
from difflib import SequenceMatcher

DB_NAME = "news.db"

# 初始化資料庫與資料表
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            title TEXT,
            source TEXT,
            url TEXT UNIQUE,
            summary TEXT DEFAULT '尚未啟用 AI',
            importance TEXT DEFAULT '一般',
            impact_companies TEXT DEFAULT '未標註',
            cluster_id TEXT,
            report_count INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

# 計算兩標題相似度
def title_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()

# 抓取 Google News RSS 並寫入資料庫（含簡易去重與計數）
def fetch_and_store_news(keyword="台股"):
    init_db()
    rss_url = f"https://news.google.com/rss/search?q={keyword}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    new_records = []
    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")
        pub_date = entry.get("published", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 解析來源（Google News 標題通常格式為 "標題 - 來源"）
        source = "未知來源"
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            title = parts[0]
            source = parts[1]

        new_records.append({
            "date": pub_date,
            "title": title,
            "source": source,
            "url": link
        })

    inserted_count = 0
    for item in new_records:
        try:
            # 檢查是否有高度相似的既有新聞（簡單去重邏輯）
            cursor.execute("SELECT id, title, report_count FROM news")
            existing = cursor.fetchall()
            
            matched_id = None
            for row in existing:
                db_id, db_title, db_count = row[0], row[1], row[2]
                if title_similarity(item["title"], db_title) > 0.65:
                    matched_id = db_id
                    current_count = db_count
                    break
            
            if matched_id:
                # 若相似則更新報導數量
                cursor.execute("""
                    UPDATE news 
                    SET report_count = ? 
                    WHERE id = ?
                """, (current_count + 1, matched_id))
            else:
                # 若不相似則新增記錄
                cluster_id = f"cls_{datetime.now().strftime('%Y%m%d%H%M%S')}_{inserted_count}"
                cursor.execute("""
                    INSERT INTO news (date, title, source, url, cluster_id, report_count)
                    VALUES (?, ?, ?, ?, ?, 1)
                """, (item["date"], item["title"], item["source"], item["url"], cluster_id))
                inserted_count += 1
                
            conn.commit()
        except sqlite3.IntegrityError:
            # 網址重複則略過
            pass
            
    conn.close()
    return inserted_count

# 從資料庫讀取新聞供前端顯示
def get_news_from_db(search_query=""):
    init_db()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if search_query:
        cursor.execute("""
            SELECT date, title, source, url, summary, importance, impact_companies, report_count 
            FROM news 
            WHERE title LIKE ? OR impact_companies LIKE ?
            ORDER BY date DESC
        """, (f"%{search_query}%", f"%{search_query}%"))
    else:
        cursor.execute("""
            SELECT date, title, source, url, summary, importance, impact_companies, report_count 
            FROM news 
            ORDER BY date DESC
        """)
        
    rows = cursor.fetchall()
    conn.close()
    return rows
